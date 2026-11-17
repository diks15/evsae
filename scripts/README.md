# Scripts

| Script | Platform | Purpose |
|:--|:--|:--|
| `build_portable.ps1` | Windows (PowerShell) | Builds the self-contained Windows app with PyInstaller into `dist\EVSAE` and zips it into `release\`. Options: `-IncludeModels @("small","medium")` to bundle Whisper models, `-SkipZip` to only build the folder. Requires `pip install pyinstaller`. |
| `build_source_zip.py` | any | Writes `release/EVSAE-source (Linux-MacOS).zip` with Unix path separators and an executable `EVSAE_macOS.command`. |

PyInstaller cannot cross-compile: a native macOS or Linux bundle must be built
on that operating system.

The batch scripts used to process the research datasets reported in the
article are not included, because they reference recordings of human
participants that cannot be shared.
