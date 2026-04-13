import os
from modules.airtable_writer import find_record_by_fragment

base_id = os.environ.get("AIRTABLE_BASE_ID")
table_id = os.environ.get("AIRTABLE_TABLE_ID")

# Test avec le fragment extrait du PDF test
fragment = "16426B3"

record_id = find_record_by_fragment(base_id, table_id, fragment)

if record_id:
    print("Enregistrement trouve: " + record_id)
else:
    print("Aucun enregistrement trouve pour fragment: " + fragment)
