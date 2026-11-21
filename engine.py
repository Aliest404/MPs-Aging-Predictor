"""Verified saved-model inference and CSV/XLSX input handling.
No fit, tuning, automatic imputation or live multivariate AD is performed.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
import pickle
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

ASSETS = Path(__file__).resolve().parent / 'assets'
GROUP_FIELDS = ('Polymer','Aging_type','Aging_mode','Medium','Aging_reagent')
NUMERIC_FIELDS = ('pH','Aging_time_d','Temperature_C','Lamp_power_W','Wavelength_nm','Irradiance_W_m2','Particle_size_um')
INPUT_FIELDS = ('Sample_ID',)+GROUP_FIELDS+NUMERIC_FIELDS
_SUBSCRIPTS = str.maketrans('₀₁₂₃₄₅₆₇₈₉','0123456789')

def canonical(value: Any) -> str:
    if value is None or (not isinstance(value,(str,list,dict)) and pd.isna(value)):
        return ''
    return str(value).strip().translate(_SUBSCRIPTS)

def apply_medium_rules(record: dict) -> dict:
    """Return the effective model inputs; unknown media remain invalid."""
    result=dict(record)
    medium=canonical(result.get('Medium')).casefold()
    known={'water','seawater','air','soil','sludge','sediment slurry'}
    if medium in known:
        if medium != 'water':result['Aging_reagent']='nan'
        if medium not in ('water','seawater'):result['pH']=7.0
    return result

def read_inputs(path: str | Path) -> pd.DataFrame:
    path=Path(path)
    if path.suffix.lower()=='.csv':
        with path.open(encoding='utf-8-sig',newline='') as h:
            header=next(csv.reader(h),[])
        if len(header)!=len(set(header)):
            raise ValueError('Duplicate column names in input file.')
        frame=pd.read_csv(path,encoding='utf-8-sig',keep_default_na=False,dtype=str)
    elif path.suffix.lower()=='.xlsx':
        from openpyxl import load_workbook
        workbook=load_workbook(path,read_only=True,data_only=True)
        try:header=list(next(workbook.worksheets[0].values,[]))
        finally:workbook.close()
        if len(header)!=len(set(header)):
            raise ValueError('Duplicate column names in input file.')
        frame=pd.read_excel(path,engine='openpyxl',keep_default_na=False,dtype={'Sample_ID':str})
    else:
        raise ValueError('Please use a CSV or XLSX input file.')
    missing=[c for c in INPUT_FIELDS if c!='Sample_ID' and c not in frame]
    if missing:raise ValueError('Missing input columns: '+', '.join(missing))
    if frame.empty:raise ValueError('The input file has no sample rows.')
    if 'Sample_ID' not in frame:
        frame.insert(0,'Sample_ID',[f'Sample_{i+1}' for i in range(len(frame))])
    return frame

def write_results(path: str | Path, frame: pd.DataFrame) -> None:
    # Excel-safe text, while preserving actual numeric predictions (including negatives).
    output=frame.copy()
    for col in output.select_dtypes(include=['object','string']).columns:
        output[col]=output[col].map(lambda v: "'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v)
    output.to_csv(path,index=False,encoding='utf-8-sig',float_format='%.15g')

class Engine:
    def __init__(self, asset_dir: str | Path = ASSETS):
        self.asset_dir=Path(asset_dir)
        self.manifest=json.loads((self.asset_dir/'manifest.json').read_text(encoding='utf-8'))
        self.models={}

    def options(self, group: str) -> list[str]:
        return sorted({v for s in self.manifest['endpoints'].values() for v in s['categories'][group]},key=str.casefold)

    def _model(self, endpoint: str):
        if endpoint not in self.models:
            schema=self.manifest['endpoints'][endpoint]
            path=self.asset_dir/schema['bundle_file']
            if hashlib.sha256(path.read_bytes()).hexdigest()!=schema['bundle_sha256']:
                raise ValueError(f'{endpoint}: model asset checksum mismatch; reinstall the original package.')
            with path.open('rb') as h:bundle=pickle.load(h)
            if bundle['model'].n_features_in_!=len(schema['features']):
                raise ValueError(f'{endpoint}: fitted model feature count mismatch.')
            self.models[endpoint]=bundle
        return self.models[endpoint]

    def encode(self, endpoint: str, record: dict) -> pd.DataFrame:
        record=apply_medium_rules(record)
        schema=self.manifest['endpoints'][endpoint]
        values={c:0.0 for c in schema['features']}
        chosen={}
        for field in GROUP_FIELDS:
            text=canonical(record.get(field))
            if not text:raise ValueError(f'{field}: a selection is required.')
            mapping=schema['categories'][field]
            match=next((k for k in mapping if k.casefold()==text.casefold()),None)
            if match is None:raise LookupError(f'{field}={text!r} is not supported by {schema["label"]}.')
            values[mapping[match]]=1.0;chosen[field]=match
        for field in NUMERIC_FIELDS:
            value=record.get(field)
            try:
                if value is None or isinstance(value,bool) or (isinstance(value,str) and not value.strip()):raise ValueError()
                number=float(value)
                if not math.isfinite(number):raise ValueError()
            except (TypeError,ValueError,OverflowError):raise ValueError(f'{field}: enter a finite numeric value.') from None
            if field in ('Aging_time_d','Lamp_power_W','Wavelength_nm','Irradiance_W_m2') and number<0:
                raise ValueError(f'{field}: value cannot be negative.')
            if field=='Particle_size_um' and number<=0:raise ValueError('Particle_size_um: value must be greater than zero.')
            if field=='Temperature_C' and number< -273.15:raise ValueError('Temperature_C: below absolute zero.')
            values[field]=number
        if schema['pfp_columns']:
            polymer=chosen['Polymer']
            if polymer not in schema['pfp']:raise LookupError(f'No verified PFP mapping for {polymer}.')
            for col,bit in zip(schema['pfp_columns'],schema['pfp'][polymer],strict=True):values[col]=bit
        return pd.DataFrame([[values[c] for c in schema['features']]],columns=schema['features'])

    def predict(self, record: dict, endpoints: list[str] | None = None) -> list[dict]:
        record=apply_medium_rules(record)
        endpoints=list(self.manifest['endpoints']) if endpoints is None else list(endpoints)
        if not endpoints:raise ValueError('Select at least one endpoint.')
        results=[]
        for ep in endpoints:
            if ep not in self.manifest['endpoints']:raise ValueError(f'Unknown endpoint: {ep}')
            schema=self.manifest['endpoints'][ep]
            result={'endpoint':ep,'prediction':None,'unit':schema['unit'],'status':'unavailable',
                    'input_coverage':'not_assessed','multivariate_AD':'not_assessed','warnings':'',
                    'model':schema['model_name'],'version':self.manifest['version'],
                    'timestamp_UTC':datetime.now(timezone.utc).isoformat(timespec='seconds'),'message':''}
            if not schema['available']:
                result['message']=schema['unavailable_reason'];results.append(result);continue
            try:
                x=self.encode(ep,record)
                bundle=self._model(ep)
                scaled=bundle['scaler'].transform(x)
                model=bundle['model']
                model_input=pd.DataFrame(scaled,columns=model.feature_name_) if hasattr(model,'feature_name_') else scaled
                with threadpool_limits(limits=1):prediction=float(model.predict(model_input)[0])
                if not math.isfinite(prediction):raise ValueError('The model returned a non-finite value.')
                notices=[]
                for field,(low,high) in schema['numeric_bounds'].items():
                    if not low<=float(x.iloc[0][field])<=high:
                        notices.append(f'{field}: outside training range [{low:g}, {high:g}]')
                coverage='outside_training_range' if notices else 'within_univariate_training_ranges'
                outside_physical = prediction<0 or (ep=='CA' and prediction>180) or (ep=='Crystallinity' and prediction>100)
                if outside_physical:
                    notices.append('Outside physical range: do not interpret this result directly. Raw model output retained.')
                result.update(prediction=prediction,status='outside_physical_range' if outside_physical else 'ok',input_coverage=coverage,warnings='; '.join(notices),
                              message='Outside physical range; do not interpret directly.' if outside_physical else 'Univariate coverage only; multivariate AD not assessed.')
            except LookupError as exc:result.update(status='unsupported',message=str(exc))
            except ValueError as exc:result.update(status='invalid_input',message=str(exc))
            except Exception as exc:result.update(status='model_error',message=f'{type(exc).__name__}: {exc}')
            results.append(result)
        return results

    def predict_batch(self, frame: pd.DataFrame, endpoints: list[str] | None = None) -> pd.DataFrame:
        records=[]
        for row_no,(_,row) in enumerate(frame.iterrows(),start=1):
            sample={c:row.get(c,'') for c in INPUT_FIELDS}
            if not canonical(sample['Sample_ID']):sample['Sample_ID']=f'Sample_{row_no}'
            effective=apply_medium_rules(sample)
            original={'original_pH':sample['pH'],'original_Aging_reagent':sample['Aging_reagent']}
            adjustments=[]
            for field in ('pH','Aging_reagent'):
                before=canonical(sample[field]);after=canonical(effective[field])
                if before and before.casefold()!=after.casefold():
                    try:same=float(before)==float(after)
                    except ValueError:same=False
                    if not same:adjustments.append(f'{field}: input {before} replaced with {after} by medium rule')
            for result in self.predict(effective,endpoints):
                if adjustments:result['warnings']='; '.join(filter(None,[result['warnings'],*adjustments]))
                records.append({'row_number':row_no,**effective,**original,**result})
        return pd.DataFrame(records)
