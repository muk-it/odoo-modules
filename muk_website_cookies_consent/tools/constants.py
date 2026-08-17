from __future__ import annotations

CONSENT_COOKIE = 'muk_cookie_consent'
CONSENT_STATE_VERSION = 1

ESSENTIAL_CODE = 'essential'
UNCLASSIFIED_CODE = 'unclassified'
CORE_OPTIONAL_CATEGORY = 'marketing'

OBSERVATION_TYPES = (
    ('http', 'HTTP Cookie'),
    ('local', 'Local Storage'),
    ('session', 'Session Storage'),
    ('host', 'Third-party Host'),
)

OBSERVATION_STORAGE_TYPES = ('http', 'local', 'session')

OBSERVATION_BATCH_LIMIT = 200

CONSENT_MODE_SIGNALS = (
    'ad_storage',
    'ad_user_data',
    'ad_personalization',
    'analytics_storage',
    'functionality_storage',
    'personalization_storage',
    'security_storage',
)

CONSENT_MODE_WAIT_FOR_UPDATE = 500

CONSENT_MODE_HOSTS = (
    'googletagmanager.com',
    'google-analytics.com',
)

CONSENT_ACTIONS = (
    ('accept_all', 'Accept all'),
    ('reject_all', 'Reject all'),
    ('custom', 'Custom selection'),
    ('withdraw', 'Withdrawn'),
)

CONSENT_SOURCES = (
    ('banner', 'Consent banner'),
    ('preferences', 'Preference centre'),
    ('embed', 'Blocked embed placeholder'),
)

DEFAULT_LIFETIME_DAYS = 180
DEFAULT_LOG_RETENTION_DAYS = 1095

REGISTRY_HASH_LENGTH = 12

COOKIE_POLICY_PATH = '/cookie-policy'

BLOCKED_IFRAME_CLASSES = frozenset(
    (
        's_map',
        's_instagram_page',
        'o_facebook_page',
        'o_background_video',
        'media_iframe_video',
    )
)

BLOCKED_THIRD_PARTY_HOSTS = (
    'youtu.be',
    'youtube.com',
    'youtube-nocookie.com',
    'instagram.com',
    'instagr.am',
    'ig.me',
    'vimeo.com',
    'dailymotion.com',
    'dai.ly',
    'youku.com',
    'tudou.com',
    'facebook.com',
    'facebook.net',
    'fb.com',
    'fb.me',
    'fb.watch',
    'tiktok.com',
    'x.com',
    'twitter.com',
    't.co',
    'googletagmanager.com',
    'google-analytics.com',
    'google.com',
)
