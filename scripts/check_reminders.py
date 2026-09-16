"""One-shot reminder check, suitable for an OS scheduler while the web app is closed."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from folio.config import Settings
from folio.storage import Store
from folio.accounts import Accounts
from folio.mail import Mailer,Notifications

settings=Settings();settings.prepare()
store=Store(settings.data_dir);Accounts(store)
notifications=Notifications(store,Mailer(settings))
notifications.tick()
print("Expiry check complete. SMTP configured:",notifications.mailer.configured)
