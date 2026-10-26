
import csv

INPUT_FILE = "HH_Provider_Oct2026.csv"
OUTPUT_FILE = "home_health_agencies_clean.csv"

# Columns to keep from the official CMS dataset
columns_to_keep = [
    "State",
    "CMS Certification Number (CCN)",
    "Provider Name",
    "Address",
    "City/Town",
    "ZIP Code",
    "Telephone Number",
    "Type of Ownership",
    "Offers Nursing Care Services",
    "Offers Physical Therapy Services",
    "Offers Occupational Therapy Services",
    "Offers Speech Pathology Services",
    "Offers Medical Social Services",
    "Offers Home Health Aide Services",
    "Certification Date",
    "Quality of patient care star rating",
]

output_columns = [
    "Agency Type",
    "Agency Name",
    "CMS Certification Number",
    "Phone",
    "Address",
    "City",
    "State",
    "ZIP Code",
    "Ownership",
    "Nursing Care",
    "Physical Therapy",
    "Occupational Therapy",
    "Speech Pathology",
    "Medical Social Services",
    "Home Health Aide",
    "Certification Date",
    "Quality Star Rating",
    "Website",
    "Business Email",
    "Source",
]

seen = set()
clean_records = []

with open(INPUT_FILE, "r", encoding="utf-8-sig", newline="") as file:
    reader = csv.DictReader(file)

    for row in reader:
        # Identify each agency by its CMS certification number.
        ccn = (row.get("CMS Certification Number (CCN)") or "").strip()
        name = (row.get("Provider Name") or "").strip()
        address = (row.get("Address") or "").strip()
        state = (row.get("State") or "").strip()

        if not name:
            continue

        unique_id = ccn if ccn else f"{name}|{address}|{state}"

        if unique_id in seen:
            continue

        seen.add(unique_id)

        clean_records.append({
            "Agency Type": "Medicare-Certified Home Health",
            "Agency Name": name,
            "CMS Certification Number": ccn,
            "Phone": (row.get("Telephone Number") or "").strip(),
            "Address": address,
            "City": (row.get("City/Town") or "").strip(),
            "State": state,
            "ZIP Code": (row.get("ZIP Code") or "").strip(),
            "Ownership": (row.get("Type of Ownership") or "").strip(),
            "Nursing Care": (row.get("Offers Nursing Care Services") or "").strip(),
            "Physical Therapy": (row.get("Offers Physical Therapy Services") or "").strip(),
            "Occupational Therapy": (row.get("Offers Occupational Therapy Services") or "").strip(),
            "Speech Pathology": (row.get("Offers Speech Pathology Services") or "").strip(),
            "Medical Social Services": (row.get("Offers Medical Social Services") or "").strip(),
            "Home Health Aide": (row.get("Offers Home Health Aide Services") or "").strip(),
            "Certification Date": (row.get("Certification Date") or "").strip(),
            "Quality Star Rating": (row.get("Quality of patient care star rating") or "").strip(),
            "Website": "",
            "Business Email": "",
            "Source": "CMS Provider Data",
        })

with open(OUTPUT_FILE, "w", encoding="utf-8-sig", newline="") as file:
    writer = csv.DictWriter(file, fieldnames=output_columns)
    writer.writeheader()
    writer.writerows(clean_records)

print(f"Finished! Created {OUTPUT_FILE}")
print(f"Unique agencies exported: {len(clean_records)}")
print(f"Saved to the current folder.")
