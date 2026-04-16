import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xPy.settings')
django.setup()

from microsys.utils import collect_related_objects
from storage.models import Affiliate

affiliate = Affiliate.objects.filter(pk=1).first()
if affiliate:
    print(collect_related_objects(affiliate))
else:
    print("Affiliate 1 not found")
