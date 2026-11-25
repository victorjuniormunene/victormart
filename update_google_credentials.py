import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'construction_hub.settings')
django.setup()

from allauth.socialaccount.models import SocialApp

# Configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the environment first.
app = SocialApp.objects.get(provider='google')
app.client_id = os.environ['GOOGLE_CLIENT_ID']
app.secret = os.environ['GOOGLE_CLIENT_SECRET']
app.save()

print('Google credentials updated successfully!')
