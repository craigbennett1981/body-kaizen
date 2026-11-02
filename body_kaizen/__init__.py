"""Body Kaizen: a private, local dashboard for your health data. Run `body-kaizen --help`."""
from importlib.metadata import PackageNotFoundError, version

try: __version__ = version("body-kaizen")
except PackageNotFoundError: __version__ = "0+unknown"   # running from a source checkout that isn't installed
