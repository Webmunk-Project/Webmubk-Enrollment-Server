import base64
import datetime
import json
import random

from pathlib import Path

import arrow
import requests

from nacl.secret import SecretBox
from requests import Request

from django.utils import timezone

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/3.2/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'CHANGEME'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = False

ALLOWED_HOSTS = ['enroll.example.com']

ADMINS = [
    ('Admin', 'admin@example.com')
]

SILENCED_SYSTEM_CHECKS = ['security.W005', 'security.W021',]

# Database
# https://docs.djangoproject.com/en/3.2/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE':   'django.contrib.gis.db.backends.postgis',
        'NAME':     'circle_test',
        'USER':     'root',
        'PASSWORD': '',
        'HOST':     'localhost',
        'PORT':     '',
    }
}

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'America/New_York'

SITE_URL = 'https://%s' % ALLOWED_HOSTS[0]

BITLY_ACCESS_CODE = 'CHANGEME'

KEEPA_API_KEY = 'CHANGEME'
KEEPA_API_SLEEP_SECONDS = 1

ENROLLMENT_SECRET_KEY = 'CHANGEME' # TODO: DOC

SIMPLE_DATA_EXPORTER_SITE_NAME = 'Webmunk Enrollment'
SIMPLE_DATA_EXPORTER_OBFUSCATE_IDENTIFIERS = False
SIMPLE_DATA_EXPORT_DATA_SOURCES_PER_REPORT_JOB = 999999

PDK_EXTERNAL_CONTENT_SYMETRIC_KEY = 'CHANGEME' # TODO: DOC

AUTOMATED_EMAIL_FROM_ADDRESS = 'webmunk_study@example.com'

QUICKSILVER_MAX_TASK_RUNTIME_SECONDS = 60 * 60 * 4

SIMPLE_BACKUP_KEY = 'CHANGEME' # TODO: DOC

SIMPLE_BACKUP_AWS_REGION = 'us-east-1'
SIMPLE_BACKUP_AWS_ACCESS_KEY_ID = 'CHANGEME'
SIMPLE_BACKUP_AWS_SECRET_ACCESS_KEY = 'CHANGEME'
SIMPLE_BACKUP_DESTINATIONS = (
    's3://example-bucket',
)

PDK_API_URLS = (
    'https://server-1.example.com/data/',
    'https://server-2.example.com/data/',
)

FAUX_KEEPA_API_URLS = (
    'https://server-1.example.com/support/asin/',
    'https://server-2.example.com/support/asin/',
)

WEBMUNK_DATA_FOLLOWUP_DAYS = 28
WEBMUNK_REMINDER_DAYS_INTERVAL = 1

def WEBMUNK_UPDATE_TASKS(enrollment, ScheduledTask): # Main study
    # Implement custom task logic here.

    cutoff = datetime.date(2023, 6, 1)

    if enrollment.enrolled.date() < cutoff:

        incomplete = enrollment.tasks.filter(completed=None).exclude(slug='not-eligible')

        for task in incomplete:
            task.completed = task.active
            task.save()

        not_eligible = enrollment.tasks.filter(slug='not-eligible')

        if not_eligible.count() == 0:
            print('%s: Marking ineligible' % enrollment)

            task = 'Your email address does not match our records. If you think this is an error please reach out to the email address provided. Otherwise, click here to uninstall the extension.'

            final_url = 'https://example.com/survey?webmunk_id=%s' % enrollment.assigned_identifier

            ScheduledTask.objects.create(enrollment=enrollment, active=enrollment.enrolled, task=task, slug='not-eligible', url=final_url)
    else:
        metadata = enrollment.fetch_metadata()

        is_eligible = metadata.get('is_eligible', False)

        now = timezone.now()

        if is_eligible:
            enrollment.tasks.filter(slug='not-eligible').update(completed=now)

            if enrollment.tasks.filter(slug='amazon-fetch-initial').count() == 0:
                final_url = 'https://extension.webmunk.org/amazon-fetch'

                ScheduledTask.objects.create(enrollment=enrollment, active=now, task='Share Amazon order history', slug='amazon-fetch-initial', url=final_url)

                survey_url = 'https://example.com/survey?webmunk_id=%s' % enrollment.assigned_identifier

                when = now - datetime.timedelta(seconds=300)

                ScheduledTask.objects.create(enrollment=enrollment, active=when, task='Complete Initial Survey', slug='main-survey-initial', url=survey_url)

                next_share = now + datetime.timedelta(days=55) # 8 weeks

                final_url = 'https://extension.webmunk.org/amazon-fetch'

                ScheduledTask.objects.create(enrollment=enrollment, active=next_share, task='Update Amazon order history', slug='amazon-fetch-final', url=final_url)

            while enrollment.tasks.filter(slug='amazon-fetch', completed=None, active__lte=now).count() > 1:
                open_task = enrollment.tasks.filter(slug='amazon-fetch', completed=None, active__lte=now).order_by('active').first()

                open_task.completed = now

                metadata = open_task.fetch_metadata()

                metadata['completion_reason'] = 'Closed due to newer duplicate becoming active'

                open_task.metadata = json.dumps(metadata, indent=2)
                open_task.save()

            if enrollment.tasks.filter(slug='main-survey-final').count() == 0 and enrollment.tasks.filter(slug='amazon-fetch-final').exclude(completed=None).count() > 0:
                survey_url = 'https://example.com/survey?webmunk_id=%s' % enrollment.assigned_identifier

                ScheduledTask.objects.create(enrollment=enrollment, active=(now + datetime.timedelta(days=3)), task='Complete Final Survey', slug='main-survey-final', url=survey_url)

            if enrollment.tasks.filter(slug='uninstall-extension').count() == 0 and ((now - enrollment.enrolled).days >= 80 or (enrollment.tasks.filter(slug='main-survey-final').exclude(completed=None).count() > 0 and enrollment.tasks.filter(slug='amazon-fetch-final').exclude(completed=None).count() > 0)):
                survey_url = 'https://example.com/survey?webmunk_id=%s' % enrollment.assigned_identifier

                ScheduledTask.objects.create(enrollment=enrollment, active=now, task='Uninstall Study Browser Extension', slug='uninstall-extension', url=survey_url)

        while enrollment.tasks.filter(slug__istartswith='upload-amazon-', completed=None, active__lte=now).count() > 1:
            open_task = enrollment.tasks.filter(slug__istartswith='upload-amazon-', completed=None, active__lte=now).order_by('active').first()

            open_task.completed = now

            metadata = open_task.fetch_metadata()

            metadata['completion_reason'] = 'Closed due to newer duplicate becoming active'

            open_task.metadata = json.dumps(metadata, indent=2)
            open_task.save()

        if enrollment.tasks.all().count() == 0: # New participant, not yet verified - Give 15 minutes before declaring ineligible
            if (now - enrollment.enrolled).total_seconds() > (60 * 15) and enrollment.tasks.filter(slug='not-eligible').count() == 0:
                task = 'Your email address does not match our records. If you think this is an error please reach out to the email address provided. Otherwise, click here to uninstall the extension.'

                final_url = 'https://example.com/survey?webmunk_id=%s' % enrollment.assigned_identifier

                ScheduledTask.objects.create(enrollment=enrollment, active=enrollment.enrolled, task=task, slug='not-eligible', url=final_url)


def WEBMUNK_ASSIGN_RULES(found_enrollment, ExtensionRuleSet):
    if found_enrollment.rule_set is not None:
        return

    current_rulesets = [
        1, # Main Study (Amazon Treatment, Hide, Server 3)
        2, # Main Study (Control, No Hide or Highlight, Server 3)
        3, # Main Study (Random Treatment, Random Hide, Server 3)
    ]

    list_pk = random.choice(current_rulesets)

    selected_rules = ExtensionRuleSet.objects.filter(pk=list_pk).first()

    if selected_rules is not None:
        found_enrollment.rule_set = selected_rules
        found_enrollment.save()

WEBMUNK_LOG_DOMAINS = (
    'anthropologie.com',
    'apple.com',
    'barnesandnoble.com',
    'bathandbodyworks.com',
    'bestbuy.com',
    'bhphotovideo.com',
    'birchbox.com',
    'bodybuilding.com',
    'boxed.com',
    'chewy.com',
    'costco.com',
    'cvs.com',
    'dillards.com',
    'dollargeneral.com',
    'ebay.com',
    'etsy.com',
    'forever21.com',
    'gamestop.com',
    'gap.com',
    'gnc.com',
    'hm.com',
    'homedepot.com',
    'hsn.com',
    'iherb.com',
    'ikea.com',
    'warbyparker.com',
    'johnlewis.com',
    'kohls.com',
    'kroger.com',
    'lego.com',
    'lordandtaylor.com',
    'nyxcosmetics.com',
    'lowes.com',
    'macys.com',
    'microsoft.com',
    'neimanmarcus.com',
    'newegg.com',
    'nike.com',
    'nordstrom.com',
    'overstock.com',
    'qvc.com',
    'rakuten.com',
    'riteaid.com',
    'samsclub.com',
    'sephora.com',
    'shop.app',
    'staples.com',
    'target.com',
    'vitaminshoppe.com',
    'ulta.com',
    'urbanoutfitters.com',
    'victoriassecret.com',
    'walgreens.com',
    'walmart.com',
    'wayfair.com',
    'yoox.com',
    'zappos.com',
    'zulily.com',
    'shop.app',
)

WEBMUNK_TARGETED_BRANDS = (
    'Amazon Aware',
    'Amazon Basic Care',
    'Amazon Basics',
    'AmazonBasics',
    'Amazon Brand',
    'Amazon Collection',
    'Amazon Commercial',
    'AmazonCommercial',
    'Amazon Elements',
    'Amazon Essentials',
    'Featured from our brands',
    '206 Collective',
    'Amazing Baby',
    'Buttoned Down',
    'Cable Stitch',
    'Daily Ritual',
    'Goodthreads',
    'Isle Bay',
    'Lark & Ro',
    'Moon and Back by Hanna Andersson',
    'Mountain Falls',
    'P2N Peak Performance',
    'Pinzon',
    'Presto!',
    'Simple Joys by Carter\'s',
    'Solimo',
    'Spotted Zebra',
    # 'Fire TV', # CK Added
    # '10.Or',
    # '365 By Whole Foods Market',
    # '365 Every Day Value',
    # 'A For Awesome',
    # 'A Made For Kindle',
    # 'Afa',
    # 'Afa Authentic Food Artisan',
    # 'Afterthought',
    # 'Alexa',
    # 'Allegro',
    # 'Always Home',
    # 'Amazon Chime',
    # 'Amazon Dash',
    # 'Amazon Echo',
    # 'Amazon Edv',
    # 'Amazon English',
    # 'Amazon Game Studios',
    # 'Amazon Pharmacy',
    # 'Amazon Spheres',
    # 'Amazon Tap',
    # 'Amazon.Com',
    # 'Amazonfresh',
    # 'Arabella',
    # 'Arthur Harvey',
    # 'Azalea',
    # 'Be',
    # 'Belei',
    # 'Berry Chantilly',
    # 'Blink',
    # 'Bloom Street',
    # 'C/O',
    # 'Camp Moonlight',
    # 'Candy Island Confections',
    # 'Celebration Caffe',
    # 'Cheddar Chicks',
    # 'City Butcher',
    # 'Coastal Blue',
    # 'Common Casuals',
    # 'Common District',
    # 'Compass Road',
    # 'Cooper James',
    # 'Countdown To Zero',
    # 'Creative Galaxy',
    # 'D R',
    # 'Daisy Drive',
    # 'Dayana',
    # 'Denali',
    # 'Denim Bloom',
    # 'Due East Apparel',
    # 'Eero',
    # 'Fairfax',
    # 'Find.',
    # 'Fire',
    # 'Floodcraft Brewing Company',
    # 'Flying Ace',
    # 'Franklin & Freeman',
    # 'Fresh Fields',
    # 'Georgia Style W.B. Williams Brand Peach Salsa #1 Select',
    # 'Halo',
    # 'Happy Belly',
    # 'House Of Boho',
    # 'Hs House & Shields Clothing Company',
    # 'James & Erin',
    # 'Jump Club',
    # 'Kailee Athletics',
    # 'Kindle',
    # 'Kitzy',
    # 'League Of Outstanding Kids Look',
    # 'Lemon Label Paper Supply',
    # 'Lily Parker',
    # 'M X G',
    # 'Made For Amazon',
    # 'Madeline Kelly',
    # 'Mademark',
    # 'Mae',
    # 'Mia Noir',
    # 'Mint Lilac',
    # 'Movian',
    # 'Mr Beams',
    # 'Nature\'s Wonder',
    # 'Night Swim',
    # 'Ninja Squirrel',
    # 'Nod By Tuft&Needle',
    # 'Nupro',
    # 'Obsidian',
    # 'Ocean Blues',
    # 'One Wine',
    # 'Orchid Row',
    # 'Outerwear Index Co.',
    # 'Painted Heart',
    # 'Plumberry',
    # 'Ready When You Are',
    # 'Readyvolt',
    # 'Rebellion',
    # 'Replenish',
    # 'Ring',
    # 'Romantic Dreamers',
    # 'Scout + Ro',
    # 'Scuba Snacks',
    # 'Seeduction',
    # 'Sekoa',
    # 'Seriously Tasty',
    # 'Silly Apples',
    # 'Society New York',
    # 'Sprout Star',
    # 'Starkey Spring Water',
    # 'Strathwood',
    # 'Suite Alice',
    # 'The Establishment',
    # 'The Plus Project',
    # 'The Portland Plaid Co',
    # 'The Slumber Project',
    # 'Thirty Five Kent',
    # 'Toes In A Blanket',
    # 'Tovess',
    # 'Truity',
    # 'Vox',
    # 'Wag',
    # 'Weaczzy',
    # 'Wellspring',
    # 'Whole Foods',
    # 'Wickedly Prime',
    # 'Wonder Bound',
    # 'Wood Paper Company',
    # 'Yours Truly',
    # 'Zanie Kids',
    # 'Zappos',
    # 'Gabriella Rocha',
    # 'Bouquets',
    # 'Vigotti',
    # 'Type Z',
    # 'Lassen',
    # 'Fitzwell',
    # 'Rsvp',
    # 'Strathwood',
    # 'Care Of By Puma',
)

def WEBMUNK_UPDATE_ALL_RULE_SETS(payload):
    if ('log-elements' in payload['rules']) is False:
        payload['rules']['log-elements'] = []

    for domain in WEBMUNK_LOG_DOMAINS:
        domain_rule = {
            'filters': {
                'hostEquals': domain,
                'hostSuffix': '.%s' % domain
            },
            'load': ['title'],
            'leave': ['title']
        }

        payload['rules']['log-elements'].append(domain_rule)

    payload['rules']['rules'].insert(0, {
        'match': '.webmunk-targeted-brand .webmunk-targeted-brand',
        'remove-class': 'webmunk-targeted-brand'
    })

    brands = []

    for brand in WEBMUNK_TARGETED_BRANDS:
        brands.append(brand)

    brand_rule = {
        'add-class': 'webmunk-targeted-brand',
        'match': '.s-result-item:has(*:webmunkContainsInsensitiveAny(%s)):visible' % json.dumps(brands)
    }

    payload['rules']['rules'].insert(0, brand_rule)

    brand_rule = {
        'add-class': 'webmunk-targeted-brand',
        'match': '.s-result-item:has(*:webmunkContainsInsensitiveAny(%s)):visible' % json.dumps(brands)
    }

    payload['rules']['rules'].insert(0, brand_rule)

    brand_rule = {
        'add-class': 'webmunk-targeted-brand',
        'match': '.s-inner-result-item:has(*:webmunkContainsInsensitiveAny(%s)):visible' % json.dumps(brands)
    }

    payload['rules']['rules'].insert(0, brand_rule)

    brand_rule = {
        'add-class': 'webmunk-targeted-brand',
        'match': '.a-carousel-card:not(:has([data-video-url])):visible:has(*:webmunkContainsInsensitiveAny(%s))' % json.dumps(brands)
    }

    payload['rules']['rules'].insert(0, brand_rule)

    brand_rule = {
        'remove-class': 'webmunk-targeted-brand',
        'match': '.a-carousel-card:not(:has([data-video-url])):visible:not(:has(*:webmunkContainsInsensitiveAny(%s)))' % json.dumps(brands)
    }

    payload['rules']['rules'].insert(0, brand_rule)

    brand_rule = {
        'add-class': 'webmunk-targeted-brand',
        'match': '#value-pick-ac:has(*:webmunkContainsInsensitiveAny(%s)):not(:has([data-video-url])):visible' % json.dumps(brands)
    }

    payload['rules']['rules'].insert(0, brand_rule)

    brand_rule = {
        'add-class': 'webmunk-targeted-brand',
        'match': '.webmunk-asin-item:visible:has(*:webmunkContainsInsensitiveAny(%s))' % json.dumps(brands)
    }

    payload['rules']['rules'].insert(0, brand_rule)

    brand_rule = {
        'add-class': 'webmunk-targeted-brand',
        'match': '.webmunk-asin-item:visible:has(*:webmunkImageAltTagContainsInsensitiveAny(%s))' % json.dumps(brands)
    }

    payload['rules']['rules'].insert(0, brand_rule)

def WEBMUNK_CHECK_TASK_COMPLETE(task):
    if task.slug in ('upload-amazon-start', 'upload-amazon-final'):
        pdk_ed_url  = 'https://server.example.com/data/external/uploads/%s.json' % task.enrollment.assigned_identifier

        amazon_divider = task.enrollment.enrolled + datetime.timedelta(days=WEBMUNK_DATA_FOLLOWUP_DAYS)

        try:
            response = requests.get(pdk_ed_url)

            if response.status_code == 200:
                uploaded_items = response.json()

                for item in uploaded_items:
                    if item['source'] == 'amazon':
                        item_upload = arrow.get(item['uploaded']).datetime

                        if task.slug == 'upload-amazon-start' and item_upload < amazon_divider:
                            return True

                        if task.slug == 'upload-amazon-final' and item_upload > amazon_divider:
                            task.completed = item_upload

                            incomplete_amazon = task.enrollment.tasks.filter(slug='upload-amazon-start', completed=None).first()

                            if incomplete_amazon is not None:
                                incomplete_amazon.completed = timezone.now()

                                metadata = {}

                                if incomplete_amazon.metadata is not None and incomplete_amazon.metadata != '':
                                    metadata = json.loads(incomplete_amazon.metadata)

                                    metadata['summary'] = 'Did not upload first history file'

                                    incomplete_amazon.metadata = json.dumps(metadata, indent=2)

                                    incomplete_amazon.save()

                            return True
            else:
                print('RESP[%s]: %s -- %d' % (task.enrollment.assigned_identifier, pdk_ed_url, response.status_code))
        except requests.exceptions.ConnectionError:
            print('RESP[%s]: %s -- Unable to connect' % (task.enrollment.assigned_identifier, pdk_ed_url))

    return False

WEBMUNK_QUALTRICS_API_TOKEN = 'CHANGEME'
WEBMUNK_QUALTRICS_BASE_URL = 'https://example.com'
WEBMUNK_QUALTRICS_SURVEY_IDS = (
    ('CHANGEME_SURVEY_ID', 'main-survey-initial', WEBMUNK_QUALTRICS_BASE_URL, WEBMUNK_QUALTRICS_API_TOKEN),
    ('CHANGEME_SURVEY_ID', 'main-survey-final', WEBMUNK_QUALTRICS_BASE_URL, WEBMUNK_QUALTRICS_API_TOKEN),
)

WEBMUNK_QUALTRICS_ELIGIBILITY_SURVEY_IDS = (
    ('CHANGEME_SURVEY_ID', 'study-eligible', WEBMUNK_QUALTRICS_BASE_URL, WEBMUNK_QUALTRICS_API_TOKEN),
)

WEBMUNK_QUALTRICS_WISHLIST_SURVEY_IDS = (
    ('CHANGEME_SURVEY_ID', 'wishlist-initial', WEBMUNK_QUALTRICS_BASE_URL, WEBMUNK_QUALTRICS_API_TOKEN),
)

WEBMUNK_QUALTRICS_EXPORT_SURVEY_IDS = (
    ('CHANGEME_SURVEY_ID', 'main-survey-initial', WEBMUNK_QUALTRICS_BASE_URL, WEBMUNK_QUALTRICS_API_TOKEN),
    ('CHANGEME_SURVEY_ID', 'main-survey-final', WEBMUNK_QUALTRICS_BASE_URL, WEBMUNK_QUALTRICS_API_TOKEN),
)

WEBMUNK_MONTIORING_URLS = (
    'https://www.amazon.com/s?k=usb+cables',
    'https://www.amazon.com/s?k=batteries',
    'https://www.amazon.com/s?k=button+down+shirt',
    'https://www.amazon.com/s?k=shorts',
    'https://www.amazon.com/s?k=paper+towels',
    'https://www.amazon.com/s?k=surge+protector',
    'https://www.amazon.com/s?k=zoom+light',
    'https://www.amazon.com/s?k=towels',
    'https://www.amazon.com/s?k=baby+clothes',
    'https://www.amazon.com/s?k=diapers',
    'https://www.amazon.com/s?k=dog+food',
    'https://www.amazon.com/s?k=detergent',
    'https://www.amazon.com/s?k=zyrtec',
    'https://www.amazon.com/s?k=allegra',
    'https://www.amazon.com/s?k=tv+stand',
    'https://www.amazon.com/s?k=nintendo+switch',
    'https://www.amazon.com/s?k=laptop',
    'https://www.amazon.com/s?k=airpods',
    'https://www.amazon.com/s?k=headphones',
    'https://www.amazon.com/s?k=wireless+earbuds',
    'https://www.amazon.com/s?k=ipad',
    'https://www.amazon.com/s?k=game+of+thrones',
    'https://www.amazon.com/s?k=fire+stick',
    'https://www.amazon.com/s?k=ssd',
    'https://www.amazon.com/s?k=fitbit',
    'https://www.amazon.com/s?k=kindle',
    'https://www.amazon.com/s?k=tv',
    'https://www.amazon.com/s?k=air+fryer',
    'https://www.amazon.com/s?k=bluetooth+headphones',
    'https://www.amazon.com/s?k=roku',
    'https://www.amazon.com/s?k=toilet+paper',
    'https://www.amazon.com/s?k=external+hard+drive',
    'https://www.amazon.com/s?k=tablet',
    'https://www.amazon.com/s?k=instant+pot',
    'https://www.amazon.com/s?k=micro+sd+card',
)

WEBMUNK_STUDY_DAYS = 100

DIGEST_IGNORE_RULE_PATTERNS = (
    '.webmunk-targeted-brand.*',
    ':webmunkRandomMirror(.*)',
    '.*button.*',
    'input.*',
    '.*data-asin.*',
)


DISTRIBUTED_ASIN_SERVERS = (
    'server-1.example.com',
)

PDK_DATA_KEY = 'CHANGEME' # TODO: DOC
