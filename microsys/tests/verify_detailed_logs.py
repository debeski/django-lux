import os
import django
import sys
import time

sys.path.append('/home/debeski/xPy/microsys-pkg')
sys.path.append('/home/debeski/xPy/microsys-pkg')

from django.conf import settings
if not settings.configured:
    settings.configure(
        SECRET_KEY='secret',
        DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
        INSTALLED_APPS=[
            'django.contrib.auth',
            'django.contrib.contenttypes',
            'django.contrib.sessions',
            'microsys',
        ],
        USE_TZ=True,
    )
django.setup()
from django.core.management import call_command
call_command('migrate', verbosity=0)

from django.contrib.auth import get_user_model
from microsys.models import UserActivityLog, Profile
from microsys.signals import get_model_path
from django.apps import apps
from django.test import RequestFactory

User = get_user_model()

from microsys.middleware import _thread_locals

def run_test():
    print("--- Starting Verification---")
    
    # Clean logs
    UserActivityLog.objects.all().delete()
    
    # Create Dummy User
    username = f"testuser_{int(time.time())}"
    user = User.objects.create_user(username=username, password="password123")
    print(f"Created user: {user.username}")
    
    # Mock Middleware
    _thread_locals.USER = user
    _thread_locals.REQUEST = None 
    
    # Verify Profile Creation Log (Signal)
    logs = UserActivityLog.objects.filter(created_by=user, action="CREATE", model_name="Profile")
    if logs.exists():
        print("✅ Profile Creation Logged (Signal)")
    else:
        print("❌ Profile Creation Log MISSING")
        
    # Test 1: Update User (First Name) -> Should Log "Update User" with details
    print("\n--- Test 1: Update User Field ---")
    user.first_name = "ChangedName"
    user.save()
    
    log = UserActivityLog.objects.filter(created_by=user, action="UPDATE", model_name="user").last()
    if log:
        print(f"✅ User Update Logged: {log.details}")
        if 'first_name' in log.details and log.details['first_name']['new'] == "ChangedName":
             print("   ✅ Details Correct")
        else:
             print("   ❌ Details Incorrect")
    else:
        print("❌ User Update Log MISSING")

    # Test 2: Update Password -> Should Log "Update User" with masked details
    print("\n--- Test 2: Update Password ---")
    user.set_password("newpassword123")
    user.save()
    
    log = UserActivityLog.objects.filter(created_by=user, action="UPDATE", model_name="user").order_by('-created_at').first()
    # Note: created_at might be identical, fetch latest
    
    if log and 'password' in log.details:
        print(f"✅ Password Update Logged: {log.details}")
        if log.details['password']['new'] == "********":
            print("   ✅ Password Masked")
        else:
            print("   ❌ Password NOT Masked")
    else:
        print(f"❌ Password Update Log MISSING or invalid details. Log found: {log.details if log else 'None'}")

    # Test 3: Duplicate Prevention (Debounce)
    print("\n--- Test 3: Duplicate Prevention ---")
    # Try to log identical action immediately
    from django.utils.timezone import now
    
    # Manually call safe_log to simulate rapid actions or double signals
    log1 = UserActivityLog.safe_log(user, "TEST_ACTION", "test_model", details={'key': 'val'})
    print(f"Log 1 Created: {log1 is not None}")
    
    log2 = UserActivityLog.safe_log(user, "TEST_ACTION", "test_model", details={'key': 'val'})
    print(f"Log 2 Created: {log2 is not None} (Should be False)")
    
    if log1 and not log2:
        print("✅ Debounce Working")
    else:
        print("❌ Debounce FAILED")

    # Test 4: Profile Update (2FA)
    print("\n--- Test 4: Profile Update ---")
    profile = user.profile
    profile.is_email_2fa_enabled = True
    profile.save()
    
    log = UserActivityLog.objects.filter(created_by=user, action="UPDATE", model_name="Profile").last()
    if log:
        print(f"✅ Profile Update Logged: {log.details}")
        if 'is_email_2fa_enabled' in log.details:
            print("   ✅ Details Correct")
    else:
        print("❌ Profile Update Log MISSING")

    # Test 5: User/Profile Merge Logic
    print("\n--- Test 5: User/Profile Merge Logic ---")
    # Simulate concurrent update
    # 1. Update User
    user.last_name = "MergedName"
    user.save()
    
    # 2. Update Profile immediately
    profile.bio = "New Bio" # Assuming bio field or similar, or just force save
    # Force trigger signal with different field
    profile._original_state = {'phone': '123'}
    profile.phone = '456'
    profile.save()
    
    # Check logs: Should only be ONE log in the last few seconds (or merged details)
    recent_logs = UserActivityLog.objects.filter(created_by=user, action="UPDATE").order_by('-created_at')[:2]
    print(f"Recent Logs Count: {len(recent_logs)}")
    
    first_log = recent_logs[0]
    print(f"Latest Log Details: {first_log.details}")
    
    if 'last_name' in first_log.details and 'phone' in first_log.details:
        print("✅ Log Merged Successfully (Found both User and Profile changes)")
    else:
        print("❌ Log Merge FAILED (Details missing or split)")
        if len(recent_logs) > 1:
            print(f"   Second Log Details: {recent_logs[1].details}")

if __name__ == "__main__":
    try:
        run_test()
    except Exception as e:
        print(f"❌ Error: {e}")
