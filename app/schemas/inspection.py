from pydantic import BaseModel
from typing import Optional


class InspectionChecklistCreate(BaseModel):
    # DENR/LLDA Permits
    emb_ecc:          Optional[str] = None  
    emb_cnc:          Optional[str] = None
    pamb_clearance:   Optional[str] = None
    discharge_permit: Optional[str] = None

    # City Permits
    sanitary_permit: Optional[str] = None  
    business_permit: Optional[str] = None

    # Solid Waste Management Facility
    swm_facilities: Optional[list[str]] = None

    # Solid Waste Hauling: 
    sw_hauling: Optional[dict] = None

    has_iec_materials:  Optional[bool] = None
    proper_segregation: Optional[bool] = None

    # Wastewater Treatment
    wwt_facilities: Optional[list[str]] = None

    # Desludging
    desludging:       Optional[str] = None
    desludging_other: Optional[str] = None

    # Violations:
    violations: Optional[dict] = None

    # Summary
    summary:       Optional[str] = None
    summary_other: Optional[str] = None

    # Recommendations
    recommendations:       Optional[list[str]] = None
    recommendations_other: Optional[str] = None