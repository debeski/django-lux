import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'xPy.settings')
django.setup()

from dlux.utils import collect_related_objects

try:
    from storage.models import Affiliate
except ModuleNotFoundError:
    Affiliate = None

if Affiliate is not None:
    affiliate = Affiliate.objects.filter(pk=1).first()
    if affiliate:
        print(collect_related_objects(affiliate))
    else:
        print("Affiliate 1 not found")
