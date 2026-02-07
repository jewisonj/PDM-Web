"""Waterjet cutting time calculation service."""

from typing import Optional
from supabase import Client


def calculate_cutting_speed(
    material_code: str,
    thickness_in: float,
    supabase: Client
) -> Optional[float]:
    """
    Calculate waterjet cutting speed using power-law formula.

    Formula: speed = ref_speed * (0.25 / thickness)^exponent * machinability

    Args:
        material_code: Material code ('CS', 'AL', 'SS')
        thickness_in: Material thickness in inches
        supabase: Supabase client

    Returns:
        Cutting speed in inches per minute (IPM), or None if not found
    """
    result = supabase.table('cutting_parameters') \
        .select('ref_speed_ipm, machinability, exponent') \
        .eq('material_code', material_code) \
        .single() \
        .execute()

    if not result.data:
        return None

    params = result.data
    ref_speed = float(params['ref_speed_ipm'])
    machinability = float(params['machinability'])
    exponent = float(params['exponent'])

    # Formula: speed = ref_speed * (0.25 / thickness)^exponent * machinability
    speed = ref_speed * ((0.25 / thickness_in) ** exponent) * machinability
    return round(speed, 1)


def calculate_cut_time(
    material: str,
    thickness: float,
    cut_length: float,
    supabase: Client
) -> Optional[float]:
    """
    Calculate waterjet cut time in minutes.

    Formula: cut_time = (cut_length / cutting_speed) + handling_time

    Args:
        material: Material string from item (e.g., 'STEEL_HSLA', 'AL_6061')
        thickness: Material thickness in inches (from Creo SMT_THICKNESS)
        cut_length: Cut perimeter length in inches (from Creo CUT_LENGTH)
        supabase: Supabase client

    Returns:
        Cut time in minutes, or None if required parameters are missing
    """
    if not all([material, thickness, cut_length]):
        return None

    # Ensure numeric values
    try:
        thickness_in = float(thickness)
        cut_length_in = float(cut_length)
    except (ValueError, TypeError):
        return None

    if thickness_in <= 0 or cut_length_in <= 0:
        return None

    # Map material string to code
    material_code = map_material_to_code(material)
    if not material_code:
        return None

    # Get cutting speed (thickness and cut_length are already in inches from Creo)
    speed = calculate_cutting_speed(material_code, thickness_in, supabase)
    if not speed or speed <= 0:
        return None

    # Get handling time from cost_settings
    try:
        settings = supabase.table('cost_settings').select('handling_time_min').single().execute()
        handling_time = float(settings.data.get('handling_time_min', 0.5)) if settings.data else 0.5
    except Exception:
        handling_time = 0.5

    # Calculate: (length / speed) + handling
    cut_time = (cut_length_in / speed) + handling_time
    return round(cut_time, 2)


def map_material_to_code(material: str) -> Optional[str]:
    """
    Map item material strings to cutting parameter codes.

    Args:
        material: Material string from item (e.g., 'STEEL_HSLA', 'AL_6061', 'SS_304')

    Returns:
        Material code ('CS', 'AL', 'SS') or None if not recognized
    """
    if not material:
        return None

    material_upper = material.upper()

    # Check for aluminum
    if material_upper.startswith('AL') or 'ALUMINUM' in material_upper:
        return 'AL'

    # Check for stainless steel
    if material_upper.startswith('SS') or 'STAINLESS' in material_upper:
        return 'SS'

    # Check for carbon/mild steel (default for steel types)
    if 'STEEL' in material_upper or material_upper.startswith('CS'):
        return 'CS'

    return None
