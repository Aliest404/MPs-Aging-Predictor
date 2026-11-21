# MPs Aging Property Prediction

A desktop application for predicting four properties of aged microplastics: carbonyl index (CI), oxygen-to-carbon ratio (O/C), contact angle (CA), and crystallinity. The application supports individual predictions and CSV/XLSX batch inputs.

## Model overview

| Endpoint | Model | Input representation |
| --- | --- | --- |
| CI | HistGradientBoostingRegressor | Basic + PFP |
| O/C | LGBMRegressor | Basic |
| CA | HistGradientBoostingRegressor | Basic + PFP |
| Crystallinity | XGBRegressor | Basic |

For CI and CA, PFP features are matched automatically for the supported polymers: PA6, PBAT, PE, PET, PLA, PP, PS, and PVC. Each endpoint supports its own training categories and numerical ranges. Open **Help → Model information** in the app for model parameters and endpoint-specific details.


## Windows: install and run from source

1. Install Python 3.12 with the Python Launcher and Tkinter enabled. Internet access is needed to install dependencies.
2. Download and extract the repository, keeping the files and `assets` folder together.
3. Double-click `install_windows.bat`. It creates a local environment, installs the pinned dependencies, and verifies the saved examples.
4. Double-click `run_windows.bat` to launch the app.

Alternatively, in a terminal opened in the project folder:

```bat
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py --verify
.venv\Scripts\python main.py
```

This repository is source code plus trained model files, not a prebuilt executable. On Windows, after installation, `build_windows.bat` can create a standalone application folder in `dist`. The build process installs PyInstaller and requires internet access; distribute the complete generated folder. This Windows packaging process has not yet been tested on a Windows computer.

## Using the app

- Select a medium first. The aging reagent is selectable for Water; other media use the training category Unspecified. Enter pH for Water and SeaWater; other media automatically use pH 7. The light and other numerical fields remain required.
- The same medium rules apply to batch predictions. Exported results contain both the effective values and the original pH and reagent values from the input. Do not substitute zero for an unknown measurement.
- Select the desired endpoint and click **Model Prediction**. Use **Help → Load example** to load a recorded example.
- Use **File → Save CSV template** to create a batch template and **File → Batch prediction** to import CSV or XLSX inputs. **Export Results** saves results to CSV.
- The reagent choice **Unspecified** corresponds to a category in the training data; it does not necessarily mean no reagent was used.
- Results outside the physical range are marked with `!` and `outside_physical_range`; the raw model output is retained for review and must not be interpreted directly.
- Input warnings compare individual variables with endpoint-specific training ranges. They are not a multivariate applicability-domain assessment, a confidence interval, or a guarantee of prediction accuracy.

## Verification

Run the saved-example check without opening the GUI:

```text
python main.py --verify
```

Run the test suite after installing the dependencies:

```text
python -m unittest discover -s tests -v
```

GUI integration tests require a graphical display and are skipped when one is unavailable. The examples check that the bundled files reproduce their recorded predictions; they are not an independent external validation.

## Project files

- `main.py`, `gui.py`, `engine.py`: application entry point, interface, and prediction logic.
- `assets/`: model files, input definitions, PFP lookup, and recorded examples required by the app.
- `requirements.txt`: pinned runtime dependencies.
- `install_windows.bat`, `run_windows.bat`, `build_windows.bat`: Windows installation, launch, and packaging helpers.
- `tests/`: prediction and interface checks.

The model files use Python pickle serialization. Load only model files from a trusted source.

## 中文说明

本项目提供 CI、O/C、CA 和结晶度预测，支持单样本及批量输入；CI 和 CA 的 PFP 会按支持的聚合物自动匹配。首次使用请安装 Python 3.12，解压后依次双击 `install_windows.bat` 和 `run_windows.bat`。模型及超参数可在软件的 **Help → Model information** 查看。Water 可选择试剂，其他介质自动采用 Unspecified；Water 和 SeaWater 可输入 pH，其他介质自动设为 7。光照等其他数值字段均需填写；软件提示的输入范围并不等同于完整适用域判定。


## Citation and license

Citation and license information may be added by the project owner.
