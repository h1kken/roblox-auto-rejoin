import os
from pathlib import Path


PATH_TO_LOCALAPPDATA = Path(os.environ['LOCALAPPDATA'])
PATH_TO_FISHSTRAP = PATH_TO_LOCALAPPDATA / 'Fishstrap' / 'Fishstrap.exe'
