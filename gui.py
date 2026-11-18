"""Two-panel offline desktop interface for the verified prediction engine."""
from __future__ import annotations
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import pandas as pd
from engine import Engine, INPUT_FIELDS, GROUP_FIELDS, NUMERIC_FIELDS, read_inputs, write_results

BG='#f3f5f6';INK='#202c36';MUTED='#6d7882';ACCENT='#345b72';WHITE='#ffffff'
LABELS={'Polymer':'Polymer','Aging_type':'Aging type','Aging_mode':'Aging mode',
        'Medium':'Medium','Aging_reagent':'Aging reagent',
        'pH':'pH','Aging_time_d':'Aging time','Temperature_C':'Temperature',
        'Lamp_power_W':'Lamp power','Wavelength_nm':'Wavelength',
        'Irradiance_W_m2':'Irradiance','Particle_size_um':'Particle size'}
UNITS={'pH':'—','Aging_time_d':'d','Temperature_C':'°C','Lamp_power_W':'W',
       'Wavelength_nm':'nm','Irradiance_W_m2':'W/m²','Particle_size_um':'µm'}
NAN_LABEL='Unspecified (training category)'

class PredictorApp:
    def __init__(self, root: tk.Tk, engine: Engine | None=None):
        self.root=root;self.engine=engine or Engine()
        self.revision=0;self.busy=False;self.result_data=None;self._queue=queue.Queue()
        self.input_vars={};self.endpoint_vars={};self.card_values={};self.card_status={}
        self.root.title('MPs Aging Property Prediction')
        height=min(810,max(650,self.root.winfo_screenheight()-100))
        self.root.geometry(f'1160x{height}');self.root.minsize(1000,600);self.root.configure(bg=BG)
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self._build()
        for var in list(self.input_vars.values())+list(self.endpoint_vars.values()):var.trace_add('write',self.invalidate)
        self.input_vars['Medium'].trace_add('write',self._on_medium_changed)
        self._on_medium_changed()
        self._poll_id=self.root.after(80,self._poll)
        self.root.bind('<Destroy>',self._destroyed,add='+')

    def _build(self):
        style=ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('TFrame',background=WHITE)
        style.configure('TLabel',background=WHITE,foreground=INK,font=('Arial',10))
        style.configure('TCheckbutton',background=WHITE,foreground=INK,font=('Arial',10))
        style.configure('TButton',font=('Arial',10),padding=(12,7),background='#ffffff',foreground=INK,bordercolor='#cbd2d8',lightcolor='#ffffff',darkcolor='#ffffff')
        style.map('TButton',background=[('active','#eef2f4')])
        style.configure('Accent.TButton',font=('Arial',10,'bold'),padding=(18,8),background=ACCENT,foreground='#ffffff',bordercolor=ACCENT,lightcolor=ACCENT,darkcolor=ACCENT)
        style.map('Accent.TButton',background=[('active','#294c60'),('disabled','#c0c8cd')],foreground=[('disabled','#f6f6f6')])
        style.configure('TCombobox',padding=4,font=('Arial',10),fieldbackground=WHITE,background='#edf0f2',bordercolor='#ccd3d8',arrowcolor='#586771')
        style.map('TCombobox',fieldbackground=[('readonly',WHITE)])
        style.configure('TEntry',padding=4,font=('Arial',10),fieldbackground=WHITE,bordercolor='#ccd3d8',lightcolor=WHITE,darkcolor=WHITE)
        self.examples=[e for e in self.engine.manifest['examples'] if e['available']]
        self.example_names=[e['name'] for e in self.examples]
        self.example_var=tk.StringVar(value=self.example_names[0])
        menu=tk.Menu(self.root)
        file_menu=tk.Menu(menu,tearoff=False)
        file_menu.add_command(label='Batch prediction (CSV / XLSX)',command=self.browse_batch)
        file_menu.add_command(label='Save CSV template',command=self.save_template)
        file_menu.add_separator();file_menu.add_command(label='Exit',command=self.close)
        menu.add_cascade(label='File',menu=file_menu)
        help_menu=tk.Menu(menu,tearoff=False)
        help_menu.add_command(label='User guide',command=self.show_help)
        example_menu=tk.Menu(help_menu,tearoff=False)
        for i,e in enumerate(self.examples):
            example_menu.add_command(label=e['name'],command=lambda index=i:self.load_example(index))
        help_menu.add_cascade(label='Load example',menu=example_menu)
        help_menu.add_command(label='Model information',command=self.show_model_info)
        menu.add_cascade(label='Help',menu=help_menu)
        bar=ttk.Frame(self.root,padding=(23,10,23,10));bar.pack(fill='x')
        ttk.Label(bar,text='MPs Aging Property Prediction',font=('Arial',13,'bold')).pack(side='left')
        ttk.Menubutton(bar,text='Help',menu=help_menu).pack(side='right',padx=(6,0))
        ttk.Menubutton(bar,text='File',menu=file_menu).pack(side='right')
        body=tk.Frame(self.root,bg=BG);body.pack(fill='both',expand=True,padx=20,pady=(16,10))
        body.grid_columnconfigure(0,weight=49,uniform='panels');body.grid_columnconfigure(1,weight=51,uniform='panels');body.grid_rowconfigure(0,weight=1)
        left_shell=tk.Frame(body,bg=WHITE,highlightbackground='#dde2e5',highlightthickness=1);left_shell.grid(row=0,column=0,sticky='nsew',padx=(0,8))
        left_outer=ttk.Frame(left_shell,padding=(19,18,10,16));left_outer.pack(fill='both',expand=True)
        ttk.Label(left_outer,text='Data Input',font=('Arial',14,'bold')).pack(anchor='w',pady=(0,13))
        self.left_canvas,left=self._scroll_frame(left_outer);self._scroll_regions=[(self.left_canvas,left)]
        right_shell=tk.Frame(body,bg=WHITE,highlightbackground='#dde2e5',highlightthickness=1);right_shell.grid(row=0,column=1,sticky='nsew',padx=(8,0))
        right=ttk.Frame(right_shell,padding=(21,18,16,16));right.pack(fill='both',expand=True)
        ttk.Label(right,text='Prediction Results',font=('Arial',14,'bold')).pack(anchor='w',pady=(0,16))
        left.grid_columnconfigure(1,weight=1)
        ttk.Label(left,text='MATERIAL AND AGING CONDITIONS',font=('Arial',9,'bold'),foreground=MUTED).grid(row=0,column=0,columnspan=3,sticky='w',pady=(0,12))
        row=1
        available=[s for s in self.engine.manifest['endpoints'].values() if s['available']]
        for field in GROUP_FIELDS:
            ttk.Label(left,text=LABELS[field]).grid(row=row,column=0,sticky='w',pady=5,padx=(0,15))
            var=tk.StringVar();self.input_vars[field]=var
            values=sorted({v for s in available for v in s['categories'][field]},key=str.casefold)
            values=[NAN_LABEL if v=='nan' else v for v in values]
            widget=ttk.Combobox(left,textvariable=var,values=values,state='readonly',width=28)
            widget.grid(row=row,column=1,columnspan=2,sticky='ew',pady=5)
            if field=='Aging_reagent':self.reagent_widget=widget
            row+=1
            if field=='Polymer':
                ttk.Label(left,text='PFP is matched automatically for supported polymers (CI / CA).',foreground=MUTED,font=('Arial',9)).grid(row=row,column=1,columnspan=2,sticky='w',pady=(0,4))
                row+=1
        ttk.Separator(left).grid(row=row,column=0,columnspan=3,sticky='ew',pady=(10,8));row+=1
        for field in NUMERIC_FIELDS:
            ttk.Label(left,text=LABELS[field]).grid(row=row,column=0,sticky='w',pady=4,padx=(0,15))
            var=tk.StringVar();self.input_vars[field]=var
            widget=ttk.Entry(left,textvariable=var,width=20);widget.grid(row=row,column=1,sticky='ew',pady=4)
            if field=='pH':self.ph_widget=widget
            ttk.Label(left,text=UNITS[field],foreground=MUTED,width=6).grid(row=row,column=2,sticky='w',padx=(8,0));row+=1
        numeric_help=ttk.Label(left,text='pH: Water / SeaWater only; otherwise 7. Reagent: Water only. Light fields are required.',foreground=MUTED,wraplength=410)
        numeric_help.grid(row=row,column=0,columnspan=3,sticky='w',pady=(12,8))
        left.bind('<Configure>',lambda e:numeric_help.configure(wraplength=max(180,e.width-16)),add='+')
        ttk.Label(right,text='SELECT ENDPOINTS',font=('Arial',9,'bold'),foreground=MUTED).pack(anchor='w')
        choice=ttk.Frame(right);choice.pack(fill='x',pady=(10,14))
        for ep,schema in self.engine.manifest['endpoints'].items():
            var=tk.BooleanVar(value=schema['available']);self.endpoint_vars[ep]=var
            ttk.Checkbutton(choice,text=schema['label'],variable=var,state='normal' if schema['available'] else 'disabled').pack(side='left',padx=(0,10))
        self.right_canvas,result_body=self._scroll_frame(right);self._scroll_regions.append((self.right_canvas,result_body))
        headings=ttk.Frame(result_body);headings.pack(fill='x',pady=(0,5))
        ttk.Label(headings,text='Endpoint',foreground=MUTED).grid(row=0,column=0,sticky='w')
        ttk.Label(headings,text='Predicted value',foreground=MUTED).grid(row=0,column=1,sticky='w')
        headings.columnconfigure(0,weight=1);headings.columnconfigure(1,weight=1)
        ttk.Separator(result_body).pack(fill='x')
        table=ttk.Frame(result_body);table.pack(fill='x',pady=(4,12));table.columnconfigure(0,weight=1);table.columnconfigure(1,weight=1)
        for i,(ep,schema) in enumerate(self.engine.manifest['endpoints'].items()):
            ttk.Label(table,text=schema['label']+('  ('+schema['unit']+')' if schema['unit'] else ''),font=('Arial',11)).grid(row=i,column=0,sticky='w',pady=9)
            value=tk.StringVar(value='—');self.card_values[ep]=value
            ttk.Label(table,textvariable=value,font=('Arial',11,'bold')).grid(row=i,column=1,sticky='w',pady=9)
            self.card_status[ep]=tk.StringVar(value='Ready' if schema['available'] else 'Unavailable')
        ttk.Separator(result_body).pack(fill='x',pady=(0,12))
        ttk.Label(result_body,text='INPUT COVERAGE AND NOTES',font=('Arial',9,'bold'),foreground=MUTED).pack(anchor='w',pady=(0,7))
        notes=ttk.Frame(result_body);notes.pack(fill='both',expand=True)
        self.notes=tk.Text(notes,height=9,width=45,wrap='word',font=('Arial',10),bg='#f7f9fa',fg=INK,relief='flat',borderwidth=0,padx=10,pady=10,state='disabled')
        scroll=ttk.Scrollbar(notes,command=self.notes.yview);self.notes.configure(yscrollcommand=scroll.set)
        self.notes.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        self._set_notes('Enter all required inputs, then select Model Prediction.\n\nNumeric coverage is checked against each training range. Multivariate applicability domain is not assessed.')
        controls=ttk.Frame(right);controls.pack(fill='x',pady=(12,0))
        self.predict_button=ttk.Button(controls,text='Model Prediction',style='Accent.TButton',command=self.start_prediction);self.predict_button.pack(side='left')
        self.export_button=ttk.Button(controls,text='Export Results',command=self.export_results,state='disabled');self.export_button.pack(side='left',padx=8)
        self.batch_button=ttk.Button(controls,text='Batch',command=self.browse_batch)
        self.status_var=tk.StringVar(value='Ready')
        tk.Label(self.root,textvariable=self.status_var,bg=BG,fg=MUTED,font=('Arial',9),anchor='w').pack(fill='x',padx=24,pady=(0,11))
        self.root.bind('<MouseWheel>',self._wheel,add='+');self.root.bind('<Button-4>',self._wheel,add='+');self.root.bind('<Button-5>',self._wheel,add='+')

    def _scroll_frame(self,parent):
        frame=ttk.Frame(parent);frame.pack(fill='both',expand=True)
        canvas=tk.Canvas(frame,bg=WHITE,highlightthickness=0,width=1,height=1)
        scroll=ttk.Scrollbar(frame,orient='vertical',command=canvas.yview)
        def update_scrollbar(first,last):
            scroll.set(first,last)
            if float(first)<=0.0 and float(last)>=1.0:
                if scroll.winfo_manager():scroll.pack_forget()
            elif not scroll.winfo_manager():
                scroll.pack(side='right',fill='y',before=canvas)
        canvas.configure(yscrollcommand=update_scrollbar)
        scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        content=ttk.Frame(canvas,padding=(3,2,8,2))
        item=canvas.create_window((0,0),window=content,anchor='nw')
        content.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(item,width=e.width))
        return canvas,content

    def _wheel(self,event):
        if isinstance(event.widget,(tk.Text,ttk.Combobox)):return
        for canvas,content in self._scroll_regions:
            widget=event.widget
            while widget is not None:
                if widget is content or widget is canvas:
                    step=-1 if getattr(event,'num',None)==4 else (1 if getattr(event,'num',None)==5 else (-1 if event.delta>0 else 1))
                    canvas.yview_scroll(step*3,'units');return
                widget=getattr(widget,'master',None)

    def _set_notes(self,text):
        self.notes.configure(state='normal');self.notes.delete('1.0','end');self.notes.insert('1.0',text);self.notes.configure(state='disabled')

    def _on_medium_changed(self,*_):
        medium=self.input_vars['Medium'].get().strip().casefold()
        self.reagent_widget.configure(state='readonly' if medium=='water' else 'disabled')
        self.ph_widget.configure(state='normal' if medium in ('water','seawater') else 'disabled')
        if medium and medium!='water':self.input_vars['Aging_reagent'].set(NAN_LABEL)
        if medium and medium not in ('water','seawater'):self.input_vars['pH'].set('7')

    def collect_record(self):
        record={'Sample_ID':'Single_sample'}
        for field,var in self.input_vars.items():
            value=var.get().strip();record[field]='nan' if field=='Aging_reagent' and value==NAN_LABEL else value
        return record

    def invalidate(self,*_):
        self.revision+=1;self.result_data=None;self.export_button.state(['disabled'])
        for ep,s in self.engine.manifest['endpoints'].items():
            self.card_values[ep].set('—');self.card_status[ep].set('Ready' if s['available'] else 'Unavailable')
        self.status_var.set('Inputs changed · run prediction to update results.')
        self._set_notes('Results cleared after an input change.\n\nInput coverage is a check of individual training ranges. Multivariate AD is not assessed.')

    def load_example(self,index=None):
        if index is None:index=self.example_names.index(self.example_var.get())
        record=self.examples[index]['record']
        for field,var in self.input_vars.items():var.set(NAN_LABEL if field=='Aging_reagent' and record[field]=='nan' else str(record[field]))
        self.status_var.set('Loaded '+self.examples[index]['name']+' · click Model Prediction.')

    def _selected(self):return [ep for ep,v in self.endpoint_vars.items() if v.get()]

    def _start_job(self,fn,kind):
        if self.busy:return
        self.invalidate();revision=self.revision;self.busy=True
        self.predict_button.state(['disabled']);self.batch_button.state(['disabled'])
        self.status_var.set('Predicting…')
        def worker():
            try:self._queue.put((revision,kind,fn(),None))
            except Exception as exc:self._queue.put((revision,kind,None,str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def start_prediction(self):
        record=self.collect_record();endpoints=self._selected()
        if not endpoints:self.status_var.set('Select at least one available endpoint.');return
        self._start_job(lambda:self.engine.predict_batch(pd.DataFrame([record]),endpoints),'single')

    def start_batch(self,path):
        endpoints=self._selected()
        if not endpoints:self.status_var.set('Select at least one available endpoint.');return
        self._start_job(lambda:self.engine.predict_batch(read_inputs(path),endpoints),'batch')

    def browse_batch(self):
        path=filedialog.askopenfilename(parent=self.root,title='Batch prediction',filetypes=[('Inputs','*.csv *.xlsx')])
        if path:self.start_batch(path)

    def _poll(self):
        try:
            revision,kind,frame,error=self._queue.get_nowait();self.busy=False
            self.predict_button.state(['!disabled']);self.batch_button.state(['!disabled'])
            if revision!=self.revision:
                self.status_var.set('Inputs changed during prediction · run again.');return
            if error:
                self.status_var.set('Prediction failed · see notes.');self._set_notes(error);return
            self.result_data=frame;self.export_button.state(['!disabled'])
            lines=[]
            for ep,s in self.engine.manifest['endpoints'].items():
                rows=frame[frame['endpoint']==ep]
                if rows.empty:
                    if s['available']:self.card_status[ep].set('Not selected')
                    continue
                good=rows[rows['status']=='ok']
                if kind=='single':
                    result=rows.iloc[0]
                    self.card_values[ep].set(f'{result["prediction"]:.5g}  !' if result['status']=='outside_physical_range' else (f'{result["prediction"]:.5g}' if result['status']=='ok' else '—'))
                    self.card_status[ep].set('Outside training range' if result['input_coverage']=='outside_training_range' else ('Training ranges checked' if result['status']=='ok' else result['status'].replace('_',' ').title()))
                else:
                    self.card_values[ep].set(f'{len(good)} / {len(rows)}')
                    self.card_status[ep].set('successful batch predictions')
            for _,r in frame.head(60).iterrows():
                text=f'{r["Sample_ID"]} · {self.engine.manifest["endpoints"][r["endpoint"]]["label"]}: '
                if r['status'] in ('ok','outside_physical_range'):
                    text+=f'{r["prediction"]:.6g} {r["unit"]}\n'
                    text+=('  Outside individual training ranges.' if r['input_coverage']=='outside_training_range' else '  Within individual training ranges.')
                    if r['warnings']:text+='\n  '+r['warnings']
                else:text+=r['message']
                lines.append(text)
            lines.append('\nMultivariate AD: not assessed. Input coverage does not guarantee prediction accuracy.')
            if len(frame)>60:lines.append('Showing the first 60 outputs. Export CSV for every sample and status.')
            self._set_notes('\n\n'.join(lines))
            ok=int((frame['status']=='ok').sum());physical=int((frame['status']=='outside_physical_range').sum())
            self.status_var.set(f'Warning: {physical} result(s) outside physical range · see notes.' if physical else f'Completed · {ok}/{len(frame)} successful endpoint predictions · export includes inputs and notes.')
        except queue.Empty:pass
        finally:
            if self.root.winfo_exists():self._poll_id=self.root.after(80,self._poll)

    def template_to_path(self,path):
        pd.DataFrame([self.examples[0]['record']],columns=INPUT_FIELDS).to_csv(path,index=False,encoding='utf-8-sig')

    def save_template(self):
        path=filedialog.asksaveasfilename(parent=self.root,title='Save input template',initialfile='MPs_ML_input_template.csv',defaultextension='.csv',filetypes=[('CSV','*.csv')])
        if path:
            try:self.template_to_path(path);self.status_var.set('Template saved · replace the example row with your inputs.')
            except OSError as exc:messagebox.showerror('Could not save',str(exc),parent=self.root)

    def export_to_path(self,path):
        if self.result_data is None:raise ValueError('Run prediction before exporting results.')
        write_results(path,self.result_data)

    def export_results(self):
        if self.result_data is None:return
        path=filedialog.asksaveasfilename(parent=self.root,title='Export results',initialfile='MPs_ML_predictions.csv',defaultextension='.csv',filetypes=[('CSV','*.csv')])
        if path:
            try:self.export_to_path(path);self.status_var.set('Results exported with input conditions and coverage notes.')
            except OSError as exc:messagebox.showerror('Could not export',str(exc),parent=self.root)

    def _text_window(self,title,text):
        top=tk.Toplevel(self.root);top.title(title);top.geometry('790x610')
        view=tk.Text(top,wrap='word',font=('Arial',11),padx=22,pady=20)
        scroll=ttk.Scrollbar(top,command=view.yview);view.configure(yscrollcommand=scroll.set)
        view.pack(side='left',fill='both',expand=True);scroll.pack(side='right',fill='y')
        view.insert('1.0',text);view.configure(state='disabled')

    def show_help(self):
        self._text_window('Help · MPs Aging Predictor',
            '1. Choose polymer, aging type, mode, medium and reagent.\n'
            '2. Enter the numeric fields using the displayed units. pH is set to 7 outside Water and SeaWater.\n'
            '3. Choose endpoints, then click Model Prediction.\n'
            '4. Export CSV to retain predictions, inputs and coverage notes.\n\n'
            'PFP fingerprints\nCI and CA use a verified polymer lookup for PA6, PBAT, PE, PET, PLA, PP, PS and PVC. Unknown polymers are rejected.\n\n'
            'Inputs\nFor Water, choose an aging reagent; otherwise the training category Unspecified is applied. For Water and SeaWater enter pH; other media use pH 7. Light fields remain required. Do not replace an unknown measurement with zero. The reagent option “Unspecified (training category)” refers to a category used in training.\n\n'
            'Units\nAging time: days; size: µm; temperature: °C; power: W; wavelength: nm; irradiance: W/m². O/C and CI follow the original training definitions; CA is in degrees; crystallinity is in %.\n\n'
            'Input coverage\nEach numeric variable is compared with its endpoint-specific training range. Categories and PFP must be supported. Being within individual ranges is not a multivariate AD result or a confidence interval. IF/LOF/Williams residual checks are not enabled for new samples.\n\n'
            'Batch prediction\nDownload the CSV template, replace its example row, and import CSV or XLSX. Medium rules apply to all rows; exports include original and effective pH and reagent. Invalid rows remain in the exported file with their status.\n\n'
            'Examples\nExamples are provided to demonstrate the input format and verify operation.\n\n'
            'No continuous internet connection is required after installation. Prediction values outside physical bounds are shown unchanged with a warning.')

    def show_model_info(self):
        text=['Model information',
              'Performance below is Test-set performance; it is not a single-prediction error guarantee.\n']
        for ep,s in self.engine.manifest['endpoints'].items():
            p=s['performance']['test'];r2=p.get('R2_test');rmse=p.get('RMSE_test');mae=p.get('MAE_test')
            text.append(f'{s["label"]} · {s["model_name"]}\n'
                        f'Status: {"Verified and active" if s["available"] else "Pending formal fitted model"}\n'
                        f'Inputs: {len(s["features"])} model columns; {len(s["pfp_columns"])} PFP columns.\n'
                        f'Train N={s["N_train"]}; Test N={s["N_test"]}\n'
                        f'Test R²={r2:.4f}; RMSE={rmse:.4f}; MAE={mae:.4f}\n')
            tuned={
                'CI':['learning_rate','max_iter','min_samples_leaf','max_depth','l2_regularization'],
                'CA':['learning_rate','max_iter','min_samples_leaf','max_depth','l2_regularization'],
                'OC':['boosting_type','colsample_bytree','learning_rate','max_depth','min_child_samples','min_child_weight','min_split_gain','n_estimators','num_leaves','reg_alpha','reg_lambda','subsample','subsample_freq'],
                'Crystallinity':['n_estimators','learning_rate','max_depth','gamma','min_child_weight','subsample','colsample_bytree']}
            params=self.engine._model(ep)['model'].get_params()
            text.append('Reported parameter settings:\n'+'\n'.join(f'  {name} = {params[name]}' for name in tuned[ep]))
            text.append('Additional estimator settings (including defaults):\n'+'\n'.join(f'  {name} = {value}' for name,value in sorted(params.items()) if name not in tuned[ep])+'\n')
        text.append('Models use their associated preprocessing; no fitting is performed when a prediction is requested.\n\n'
                    'Test-set metrics describe model performance on the corresponding test set.')
        self._text_window('Model information','\n'.join(text))

    def _destroyed(self,event):
        if event.widget is self.root:
            try:self.root.after_cancel(self._poll_id)
            except tk.TclError:pass

    def close(self):self.root.destroy()
