"""Catch wrong raw encoding, unsupported defaults and batch/state loss."""
import sys
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

EXAMPLE={'Sample_ID':'reference_3','Polymer':'PE','Aging_type':'Artificial','Aging_mode':'UV','Medium':'Air','Aging_reagent':'nan',
         'pH':7.0,'Aging_time_d':15.0,'Temperature_C':25.0,'Lamp_power_W':305.801136363636,
         'Wavelength_nm':365.0,'Irradiance_W_m2':600.0,'Particle_size_um':129.0}

class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from engine import Engine
        cls.engine=Engine()

    def test_raw_example_reproduces_original_ci(self):
        r=self.engine.predict(EXAMPLE,['CI'])[0]
        self.assertEqual(r['status'],'ok')
        self.assertAlmostEqual(r['prediction'],0.4824235459769924,places=10)
        self.assertEqual(r['multivariate_AD'],'not_assessed')

    def test_unknown_category_is_rejected(self):
        for field in ['Polymer','Aging_mode','Medium','Aging_reagent']:
            with self.subTest(field=field):
                r=self.engine.predict({**EXAMPLE,'Medium':'Water',field:'UNKNOWN'},['CI'])[0]
                self.assertEqual(r['status'],'unsupported');self.assertIsNone(r['prediction'])

    def test_unsupported_endpoint_does_not_block_supported_endpoint(self):
        r=self.engine.predict({**EXAMPLE,'Aging_mode':'Thermal'},['CI','CA'])
        self.assertEqual([x['status'] for x in r],['ok','unsupported'])

    def test_missing_and_nonfinite_numerics_are_rejected(self):
        for v in ['',None,np.nan,np.inf,'-inf']:
            r=self.engine.predict({**EXAMPLE,'Medium':'Water','pH':v},['CI'])[0]
            self.assertEqual(r['status'],'invalid_input');self.assertIsNone(r['prediction'])

    def test_medium_rules_apply_to_single_and_batch(self):
        for medium in ('Air','Soil','Sludge','Sediment slurry'):
            with self.subTest(medium=medium):
                rec={**EXAMPLE,'Medium':medium,'Aging_reagent':'H2O2','pH':'5.3'}
                out=self.engine.predict_batch(pd.DataFrame([rec]),['OC']).iloc[0]
                self.assertEqual(out['Aging_reagent'],'nan')
                self.assertEqual(float(out['pH']),7.0)
                self.assertEqual(out['original_Aging_reagent'],'H2O2')
                self.assertEqual(out['original_pH'],'5.3')
                self.assertIn('replaced',out['warnings'])
                x=self.engine.encode('OC',rec).iloc[0]
                self.assertEqual(x['Aging_Reagent_nan'],1)
                self.assertEqual(x['Aging_Reagent_H2O2'],0)
                self.assertEqual(x['pH'],7)
        for medium in ('Water','SeaWater'):
            rec={**EXAMPLE,'Medium':medium,'Aging_reagent':'H2O2','pH':'8.2'}
            out=self.engine.predict_batch(pd.DataFrame([rec]),['OC']).iloc[0]
            self.assertEqual(float(out['pH']),8.2)
            self.assertEqual(out['Aging_reagent'],'H2O2' if medium=='Water' else 'nan')
        self.assertEqual(self.engine.predict({**EXAMPLE,'Medium':'Water','pH':''},['OC'])[0]['status'],'invalid_input')
        self.assertEqual(self.engine.predict({**EXAMPLE,'Medium':'SeaWater','pH':''},['OC'])[0]['status'],'invalid_input')
        self.assertEqual(self.engine.predict({**EXAMPLE,'Medium':'UNKNOWN'},['OC'])[0]['status'],'unsupported')

    def test_negative_time_is_rejected_but_negative_temperature_allowed(self):
        self.assertEqual(self.engine.predict({**EXAMPLE,'Aging_time_d':-1},['CI'])[0]['status'],'invalid_input')
        self.assertEqual(self.engine.predict({**EXAMPLE,'Temperature_C':-5},['CI'])[0]['status'],'ok')

    def test_range_warning_does_not_claim_domain_membership(self):
        r=self.engine.predict({**EXAMPLE,'Aging_time_d':731},['CI'])[0]
        self.assertEqual(r['status'],'ok');self.assertEqual(r['input_coverage'],'outside_training_range')
        self.assertIn('Aging_time_d',r['warnings']);self.assertEqual(r['multivariate_AD'],'not_assessed')

    def test_crystallinity_predicts_recorded_example(self):
        e=next(e for e in self.engine.manifest['examples'] if e['endpoint']=='Crystallinity')
        r=self.engine.predict(e['record'],['Crystallinity'])[0]
        self.assertEqual(r['status'],'ok')
        self.assertAlmostEqual(r['prediction'],e['expected'],places=5)
        self.assertAlmostEqual(r['prediction'],41.85749435424805,places=5)

    def test_out_of_range_prediction_is_flagged_and_preserved(self):
        ex={'Sample_ID':'OC_Test_1','Polymer':'PE','Aging_type':'Pristine','Aging_mode':'Pristine','Medium':'Air','Aging_reagent':'nan','pH':7.0,'Aging_time_d':0.0,'Temperature_C':25.0,'Lamp_power_W':305.801136363636,'Wavelength_nm':364.0,'Irradiance_W_m2':215.417254004577,'Particle_size_um':148.0}
        r=self.engine.predict(ex,['OC'])[0]
        self.assertAlmostEqual(r['prediction'],-0.1632772825211972,places=10)
        self.assertEqual(r['status'],'outside_physical_range')
        self.assertIn('physical',r['warnings'].lower())
        out=self.engine.predict_batch(pd.DataFrame([ex]),['OC'])
        self.assertEqual(out.iloc[0]['status'],'outside_physical_range')
        self.assertAlmostEqual(out.iloc[0]['prediction'],r['prediction'])

    def test_oc_example_matches_recorded_test_sample(self):
        e=next(e for e in self.engine.manifest['examples'] if e['endpoint']=='OC')
        r=self.engine.predict(e['record'],['OC'])[0]
        self.assertEqual(r['status'],'ok')
        self.assertAlmostEqual(r['prediction'],0.144196032162803,places=10)
        ci=next(e for e in self.engine.manifest['examples'] if e['endpoint']=='CI')
        self.assertNotEqual({k:v for k,v in e['record'].items() if k != 'Sample_ID'}, {k:v for k,v in ci['record'].items() if k != 'Sample_ID'})

    def test_batch_single_equivalence_and_error_row_retention(self):
        frame=pd.DataFrame([EXAMPLE,{**EXAMPLE,'Sample_ID':'bad','Medium':'Water','pH':'oops'}])
        out=self.engine.predict_batch(frame,['CI','CA'])
        self.assertEqual(len(out),4)
        self.assertAlmostEqual(out.iloc[0]['prediction'],0.4824235459769924,places=10)
        self.assertEqual(list(out['row_number']),[1,1,2,2])
        self.assertEqual(list(out['status']),['ok','ok','invalid_input','invalid_input'])
        self.assertIn('Polymer',out.columns)

    def test_csv_keeps_leading_zero_sample_identifiers(self):
        from engine import read_inputs
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'ids.csv'
            pd.DataFrame([{**EXAMPLE,'Sample_ID':'0001'},{**EXAMPLE,'Sample_ID':'1'}]).to_csv(p,index=False)
            self.assertEqual(read_inputs(p)['Sample_ID'].tolist(),['0001','1'])

    def test_xlsx_rejects_duplicate_conflicting_numeric_headers(self):
        from engine import read_inputs
        import zipfile
        from xml.sax.saxutils import escape
        # Deliberately ambiguous minimal OOXML input, not a generated deliverable.
        headers=list(EXAMPLE)+['pH'];values=list(EXAMPLE.values())+['not_a_number']
        def row(values):
            return '<row>'+''.join('<c t="inlineStr"><is><t>'+escape(str(v))+'</t></is></c>' for v in values)+'</row>'
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'duplicates.xlsx'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('[Content_Types].xml','<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
                z.writestr('_rels/.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
                z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Inputs" sheetId="1" r:id="rId1"/></sheets></workbook>')
                z.writestr('xl/_rels/workbook.xml.rels','<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
                z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+row(headers)+row(values)+'</sheetData></worksheet>')
            with self.assertRaisesRegex(ValueError,'Duplicate'):
                read_inputs(p)

    def test_csv_import_preserves_literal_nan_reagent(self):
        from engine import read_inputs,write_results
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'input.csv';pd.DataFrame([EXAMPLE]).to_csv(p,index=False)
            frame=read_inputs(p)
            self.assertEqual(frame.iloc[0]['Aging_reagent'],'nan')
            self.assertEqual(self.engine.predict_batch(frame,['CI']).iloc[0]['status'],'ok')
            out=Path(td)/'out.csv';write_results(out,self.engine.predict_batch(frame,['CI']))
            result=pd.read_csv(out)
            self.assertAlmostEqual(result.iloc[0]['prediction'],0.4824235459769924,places=10)
