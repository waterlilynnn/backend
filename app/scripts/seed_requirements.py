"""
Run this once to populate tbl_hauler_requirements with default requirements per hauler type.

Usage (from backend/ directory):
    python -m app.scripts.seed_requirements
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal, engine, Base
from app.models.requirement import HaulerRequirement
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default requirements per hauler type
# Adjust these to match what CENRO actually requires
REQUIREMENTS = {
    "Barangay": [
        ("Barangay clearance",           "Official clearance from the barangay",                     True,  1),
        ("Business permit (BPLO)",       "Current year business permit from BPLO",                   True,  2),
        ("Waste management plan",        "Approved waste segregation and disposal plan",              True,  3),
        ("Proof of address",             "Lease contract or certificate of ownership",                True,  4),
        ("BIN registration",             "Business Identification Number from BIR or city",          True,  5),
        ("Health certificate",           "Valid health certificate for food-related businesses",      False, 6),
        ("Sanitary permit",              "Valid sanitary permit from City Health Office",             False, 7),
    ],
    "City": [
        ("Mayor's permit",               "Current year mayor's permit",                              True,  1),
        ("EMC application form",         "Duly accomplished EMC application form",                   True,  2),
        ("Waste management plan",        "Approved waste segregation and disposal plan",              True,  3),
        ("Proof of address",             "Lease contract or certificate of ownership",                True,  4),
        ("BIN registration",             "Business Identification Number",                            True,  5),
        ("Fire safety inspection cert.", "Valid FSIC from BFP",                                      True,  6),
        ("Zoning clearance",             "Clearance from the Zoning Office",                         False, 7),
    ],
    "Accredited": [
        ("Accreditation certificate",    "Valid accreditation certificate from CENRO",               True,  1),
        ("Mayor's permit",               "Current year mayor's permit",                              True,  2),
        ("EMC application form",         "Duly accomplished EMC application form",                   True,  3),
        ("Waste transport manifest",     "DOE/DENR approved waste transport manifest",               True,  4),
        ("Vehicle registration",         "OR/CR of collection vehicles",                             True,  5),
        ("Driver's license (Prof.)",     "Professional driver's license of assigned drivers",        True,  6),
        ("Insurance cert.",              "Valid vehicle insurance certificate",                       True,  7),
        ("Waste management plan",        "Detailed solid waste management plan",                     True,  8),
    ],
    "Hazardous": [
        ("DENR permit (RA 6969)",        "Permit to transport hazardous waste per RA 6969",          True,  1),
        ("EMC application form",         "Duly accomplished EMC application form",                   True,  2),
        ("Waste transport manifest",     "Hazardous waste manifest from DENR",                       True,  3),
        ("Spill response plan",          "Documented emergency spill response procedure",             True,  4),
        ("Vehicle inspection report",    "BFP or LTO vehicle inspection for hazmat transport",       True,  5),
        ("Driver training certificate",  "Certificate of training for hazardous waste handling",     True,  6),
        ("Insurance cert.",              "Liability insurance covering hazardous incidents",          True,  7),
        ("Mayor's permit",               "Current year mayor's permit",                              True,  8),
    ],
    "Exempted": [
        ("Exemption certificate",        "Certificate of exemption from CENRO",                      True,  1),
        ("EMC application form",         "Duly accomplished EMC application form",                   True,  2),
        ("Proof of exemption basis",     "Supporting documents justifying exemption",                True,  3),
        ("Business permit (BPLO)",       "Current year business permit",                             True,  4),
    ],
    "No Contract": [
        ("EMC application form",         "Duly accomplished EMC application form",                   True,  1),
        ("Affidavit of no contract",     "Notarized affidavit stating no hauler contract",           True,  2),
        ("Waste disposal proof",         "Receipts or agreements showing own waste disposal",        True,  3),
        ("Business permit (BPLO)",       "Current year business permit",                             True,  4),
        ("Barangay clearance",           "Official clearance from the barangay",                     True,  5),
    ],
}


def seed_requirements():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        logger.info("Seeding hauler requirements...")

        total_created = 0
        for hauler_type, reqs in REQUIREMENTS.items():
            for name, desc, is_required, sort_order in reqs:
                existing = db.query(HaulerRequirement).filter(
                    HaulerRequirement.hauler_type == hauler_type,
                    HaulerRequirement.requirement_name == name,
                ).first()

                if not existing:
                    db.add(HaulerRequirement(
                        hauler_type=hauler_type,
                        requirement_name=name,
                        description=desc,
                        is_required=is_required,
                        sort_order=sort_order,
                        is_active=True,
                    ))
                    total_created += 1
                    logger.info(f"  + [{hauler_type}] {name}")
                else:
                    logger.info(f"  ~ [{hauler_type}] {name} (already exists)")

        db.commit()
        logger.info(f"\nDone. Created {total_created} new requirement entries.")

    except Exception as e:
        db.rollback()
        logger.error(f"Seeding failed: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_requirements()