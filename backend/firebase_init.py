"""
Firebase Admin SDK initialization module.
Initializes Firebase with the service account key and provides
a Firestore client for all database operations.
"""

import firebase_admin
from firebase_admin import credentials, firestore

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()
