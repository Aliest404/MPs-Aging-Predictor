"""Launch the desktop UI, or run `python main.py --verify` without a display."""
import argparse
import json
import os
from pathlib import Path
import sys
os.environ.setdefault('OMP_NUM_THREADS','1')
os.environ.setdefault('OPENBLAS_NUM_THREADS','1')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify',action='store_true',help='Verify recorded examples using the saved models; no display needed')
    args=parser.parse_args()
    if args.verify:
        from engine import Engine
        engine=Engine();failed=[]
        for example in engine.manifest['examples']:
            if not example['available']:
                print(example['endpoint']+': PENDING (formal fitted model not available)');continue
            result=engine.predict(example['record'],[example['endpoint']])[0]
            error=abs(result['prediction']-example['expected']) if result['status']=='ok' else float('inf')
            print(f'{example["endpoint"]}: {result["status"]}; abs_error={error:.3g}')
            if error>1e-6:failed.append(example['endpoint'])
        return 1 if failed else 0
    import tkinter as tk
    from gui import PredictorApp
    if sys.platform=='win32':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError,OSError):pass
    root=tk.Tk();PredictorApp(root);root.mainloop()
    return 0

if __name__=='__main__':raise SystemExit(main())
