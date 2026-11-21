"""Real Tk integration tests; requires DISPLAY (run tools/check_gui.py on Linux)."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

@unittest.skipUnless(os.getenv('DISPLAY') or sys.platform=='win32','A desktop display is required')
class GuiTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from gui import PredictorApp
        self.root=tk.Tk();self.app=PredictorApp(self.root);self.root.update()
    def tearDown(self):self.root.destroy()
    def wait_job(self):
        deadline=time.monotonic()+10
        while self.app.busy and time.monotonic()<deadline:
            self.root.update();time.sleep(.01)
        self.root.update();self.assertFalse(self.app.busy,'Prediction did not finish')
    def test_example_predict_export_and_edit_invalidation(self):
        import pandas as pd
        self.app.load_example(0);self.app.start_prediction();self.wait_job()
        row=self.app.result_data.query("endpoint == 'CI'").iloc[0]
        self.assertAlmostEqual(row['prediction'],0.4824235459769924,places=10)
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'result.csv';self.app.export_to_path(out)
            self.assertAlmostEqual(pd.read_csv(out).query("endpoint == 'CI'").iloc[0]['prediction'],0.4824235459769924,places=10)
        self.app.input_vars['Aging_time_d'].set('20');self.root.update()
        self.assertIsNone(self.app.result_data)
        self.assertTrue(self.app.export_button.instate(['disabled']))
    def test_template_import_and_batch_prediction(self):
        from engine import read_inputs
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'template.csv';self.app.template_to_path(out)
            frame=read_inputs(out);self.assertEqual(frame.iloc[0]['Aging_reagent'],'nan')
            self.app.start_batch(out);self.wait_job()
            self.assertGreaterEqual(len(self.app.result_data),1)
            self.assertEqual(self.app.result_data.iloc[0]['status'],'ok')
    def test_edit_during_prediction_discards_stale_results(self):
        self.app.load_example(0);self.app.start_prediction()
        self.app.input_vars['pH'].set('8.1');self.wait_job()
        self.assertIsNone(self.app.result_data)
        self.assertTrue(self.app.export_button.instate(['disabled']))

    def test_compact_window_keeps_status_and_actions_visible(self):
        self.root.geometry('1050x800');self.root.update()
        status=self.root.winfo_children()[-1]
        bottom=self.root.winfo_rooty()+self.root.winfo_height()
        self.assertLessEqual(status.winfo_rooty()+status.winfo_height(),bottom)
        self.assertLessEqual(self.app.export_button.winfo_rooty()+self.app.export_button.winfo_height(),bottom)

    def test_high_dpi_small_desktop_keeps_scrollable_form_reachable(self):
        self.root.tk.call('tk','scaling',2.0)
        # Recreate widgets so font metrics apply to the initial layout.
        self.root.destroy()
        import tkinter as tk
        from gui import PredictorApp
        self.root=tk.Tk();self.root.tk.call('tk','scaling',2.0)
        self.app=PredictorApp(self.root)
        self.root.geometry('1050x700');self.root.update()
        self.assertLessEqual(self.root.winfo_height(),700)
        self.app.left_canvas.yview_moveto(1.0);self.root.update()
        self.assertGreater(self.app.left_canvas.yview()[0],0)
        bottom=self.root.winfo_rooty()+self.root.winfo_height()
        self.assertLessEqual(self.app.export_button.winfo_rooty()+self.app.export_button.winfo_height(),bottom)

    def test_negative_output_is_prominently_marked(self):
        e=next(i for i,x in enumerate(self.app.examples) if x['endpoint']=='OC')
        self.app.load_example(e)
        self.app.input_vars['Medium'].set('Air')
        self.app.input_vars['Aging_type'].set('Pristine')
        self.app.input_vars['Aging_mode'].set('Pristine')
        for k,v in {'Aging_time_d':'0','Wavelength_nm':'364','Irradiance_W_m2':'215.417254004577','Particle_size_um':'148'}.items():
            self.app.input_vars[k].set(v)
        for ep,var in self.app.endpoint_vars.items():var.set(ep=='OC')
        self.app.start_prediction();self.wait_job()
        self.assertEqual(self.app.result_data.iloc[0]['status'],'outside_physical_range')
        self.assertIn('!',self.app.card_values['OC'].get())
        self.assertIn('physical range',self.app.status_var.get().lower())
        self.assertIn('physical',self.app.notes.get('1.0','end').lower())

    def test_oc_example_loads_distinct_water_sample(self):
        e=next(i for i,x in enumerate(self.app.examples) if x['endpoint']=='OC')
        self.app.load_example(e);self.root.update()
        self.assertEqual(self.app.input_vars['Medium'].get(),'Water')
        self.assertEqual(self.app.input_vars['Aging_reagent'].get(),'H2O2')
        self.assertEqual(self.app.input_vars['Aging_time_d'].get(),'0.167')
        for ep,var in self.app.endpoint_vars.items():var.set(ep=='OC')
        self.app.start_prediction();self.wait_job()
        self.assertEqual(self.app.result_data.iloc[0]['status'],'ok')
        self.assertAlmostEqual(self.app.result_data.iloc[0]['prediction'],0.144196032162803,places=10)

    def test_medium_switch_controls_and_clears_old_values(self):
        self.app.input_vars['Medium'].set('Water');self.root.update()
        self.assertEqual(str(self.app.reagent_widget.cget('state')),'readonly')
        self.assertEqual(str(self.app.ph_widget.cget('state')),'normal')
        self.app.input_vars['Aging_reagent'].set('H2O2');self.app.input_vars['pH'].set('5.4')
        self.app.input_vars['Medium'].set('Air');self.root.update()
        self.assertEqual(str(self.app.reagent_widget.cget('state')),'disabled')
        self.assertEqual(str(self.app.ph_widget.cget('state')),'disabled')
        self.assertEqual(self.app.input_vars['pH'].get(),'7')
        self.assertEqual(self.app.collect_record()['Aging_reagent'],'nan')
        self.app.input_vars['Medium'].set('SeaWater');self.root.update()
        self.assertEqual(str(self.app.reagent_widget.cget('state')),'disabled')
        self.assertEqual(str(self.app.ph_widget.cget('state')),'normal')
        self.app.input_vars['pH'].set('8.2')
        self.app.input_vars['Medium'].set('Water');self.root.update()
        self.assertEqual(str(self.app.reagent_widget.cget('state')),'readonly')
        self.assertEqual(self.app.input_vars['pH'].get(),'8.2')
        self.assertEqual(self.app.collect_record()['Aging_reagent'],'nan')

    def test_model_information_shows_four_models_and_parameters(self):
        captured=[]
        self.app._text_window=lambda title,text: captured.append((title,text))
        self.app.show_model_info()
        text=captured[0][1]
        for expected in ['HistGradientBoostingRegressor','LGBMRegressor','XGBRegressor','learning_rate','max_depth','n_estimators']:
            self.assertIn(expected,text)
        self.assertNotIn('version 0.',text)
