# inventory/services/welding_estimator.py
"""
Single Source of Truth (SSOT) for Welding Estimator computations.

All BOM estimation, cost calculation, and learning/tuning functions are pure
and deterministic. These functions are unit-testable and do not access the
database directly.

Usage:
    from inventory.services.welding_estimator import (
        seed_default_materials,
        estimate_bom,
        compute_cost,
        update_tuning,
    )
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional, TypedDict


# ==============================================================================
# TYPE DEFINITIONS
# ==============================================================================


class MaterialData(TypedDict):
    """Data structure for a welding material."""
    id: int
    code: str
    name: str
    category: str  # tube, paint, consumable, hardware, etc.
    unit: str
    price_mwk: Decimal
    quantity_in_stock: Decimal


class BOMItem(TypedDict):
    """A single item in the Bill of Materials."""
    material_code: str
    material_name: str
    category: str
    quantity: Decimal
    unit: str
    unit_price_mwk: Decimal
    line_total_mwk: Decimal


class CostBreakdown(TypedDict):
    """Detailed cost breakdown for a quote."""
    materials_cost: Decimal
    labour_cost: Decimal
    overhead_cost: Decimal
    subtotal_before_margin: Decimal
    margin_amount: Decimal
    total: Decimal
    min_price: Decimal  # Break-even price


class TuningData(TypedDict):
    """Tuning multipliers for a template."""
    tube_multiplier: Decimal
    paint_multiplier: Decimal
    consumable_multiplier: Decimal
    labour_multiplier: Decimal
    samples_count: int


@dataclass
class EstimationResult:
    """Result of BOM estimation."""
    bom: List[BOMItem]
    total_tube_length_m: Decimal
    recommended_6m_lengths: int
    wastage_factor: Decimal
    cut_list_notes: str


@dataclass
class QuoteCostResult:
    """Result of quote cost calculation."""
    bom: List[BOMItem]
    cost_breakdown: CostBreakdown
    recommended_price: Decimal
    min_price: Decimal


# ==============================================================================
# DEFAULT MATERIALS CATALOG
# ==============================================================================

DEFAULT_MATERIALS: List[Dict[str, Any]] = [
    # ===========================================================================
    # SQUARE TUBES (5.8m standard in Malawi)
    # ===========================================================================
    {"code": "TUBE_20x20", "name": "Square Tube 20x20mm (5.8m)", "category": "tube", "unit": "length_5_8m", "default_price": Decimal("12000")},
    {"code": "TUBE_25x25", "name": "Square Tube 25x25mm (5.8m)", "category": "tube", "unit": "length_5_8m", "default_price": Decimal("15000")},
    {"code": "TUBE_30x30", "name": "Square Tube 30x30mm (5.8m)", "category": "tube", "unit": "length_5_8m", "default_price": Decimal("22000")},
    {"code": "TUBE_40x40", "name": "Square Tube 40x40mm (5.8m)", "category": "tube", "unit": "length_5_8m", "default_price": Decimal("28000")},
    {"code": "TUBE_50x50", "name": "Square Tube 50x50mm (5.8m)", "category": "tube", "unit": "length_5_8m", "default_price": Decimal("38000")},
    {"code": "TUBE_60x60", "name": "Square Tube 60x60mm (5.8m)", "category": "tube", "unit": "length_5_8m", "default_price": Decimal("48000")},
    {"code": "TUBE_75x75", "name": "Square Tube 75x75mm (5.8m)", "category": "tube", "unit": "length_5_8m", "default_price": Decimal("65000")},
    
    # ===========================================================================
    # ROUND TUBES
    # ===========================================================================
    {"code": "TUBE_ROUND_20", "name": "Round Tube 20mm (5.8m)", "category": "tube", "unit": "length_5_8m", "default_price": Decimal("10000")},
    {"code": "TUBE_ROUND_25", "name": "Round Tube 25mm (5.8m)", "category": "tube", "unit": "length_5_8m", "default_price": Decimal("12000")},
    {"code": "TUBE_ROUND_32", "name": "Round Tube 32mm (5.8m)", "category": "tube", "unit": "length_5_8m", "default_price": Decimal("16000")},
    {"code": "TUBE_ROUND_38", "name": "Round Tube 38mm (5.8m)", "category": "tube", "unit": "length_5_8m", "default_price": Decimal("20000")},
    {"code": "TUBE_ROUND_50", "name": "Round Tube 50mm (5.8m)", "category": "tube", "unit": "length_5_8m", "default_price": Decimal("28000")},
    
    # ===========================================================================
    # FLAT BAR
    # ===========================================================================
    {"code": "FLAT_20x3", "name": "Flat Bar 20x3mm (6m)", "category": "flat_bar", "unit": "length_6m", "default_price": Decimal("6000")},
    {"code": "FLAT_25x3", "name": "Flat Bar 25x3mm (6m)", "category": "flat_bar", "unit": "length_6m", "default_price": Decimal("8000")},
    {"code": "FLAT_30x3", "name": "Flat Bar 30x3mm (6m)", "category": "flat_bar", "unit": "length_6m", "default_price": Decimal("10000")},
    {"code": "FLAT_40x3", "name": "Flat Bar 40x3mm (6m)", "category": "flat_bar", "unit": "length_6m", "default_price": Decimal("12000")},
    {"code": "FLAT_50x5", "name": "Flat Bar 50x5mm (6m)", "category": "flat_bar", "unit": "length_6m", "default_price": Decimal("18000")},
    
    # ===========================================================================
    # ANGLE IRON
    # ===========================================================================
    {"code": "ANGLE_25x25", "name": "Angle Iron 25x25mm (6m)", "category": "angle_iron", "unit": "length_6m", "default_price": Decimal("10000")},
    {"code": "ANGLE_30x30", "name": "Angle Iron 30x30mm (6m)", "category": "angle_iron", "unit": "length_6m", "default_price": Decimal("14000")},
    {"code": "ANGLE_40x40", "name": "Angle Iron 40x40mm (6m)", "category": "angle_iron", "unit": "length_6m", "default_price": Decimal("18000")},
    {"code": "ANGLE_50x50", "name": "Angle Iron 50x50mm (6m)", "category": "angle_iron", "unit": "length_6m", "default_price": Decimal("25000")},
    {"code": "ANGLE_60x60", "name": "Angle Iron 60x60mm (6m)", "category": "angle_iron", "unit": "length_6m", "default_price": Decimal("35000")},
    
    # ===========================================================================
    # SHEET METAL
    # ===========================================================================
    {"code": "SHEET_0.6", "name": "Sheet Metal 0.6mm (2.4x1.2m)", "category": "sheet", "unit": "sheet", "default_price": Decimal("28000")},
    {"code": "SHEET_0.8", "name": "Sheet Metal 0.8mm (2.4x1.2m)", "category": "sheet", "unit": "sheet", "default_price": Decimal("35000")},
    {"code": "SHEET_1.0", "name": "Sheet Metal 1.0mm (2.4x1.2m)", "category": "sheet", "unit": "sheet", "default_price": Decimal("45000")},
    {"code": "SHEET_1.2", "name": "Sheet Metal 1.2mm (2.4x1.2m)", "category": "sheet", "unit": "sheet", "default_price": Decimal("55000")},
    {"code": "SHEET_1.5", "name": "Sheet Metal 1.5mm (2.4x1.2m)", "category": "sheet", "unit": "sheet", "default_price": Decimal("68000")},
    {"code": "SHEET_2.0", "name": "Sheet Metal 2.0mm (2.4x1.2m)", "category": "sheet", "unit": "sheet", "default_price": Decimal("85000")},
    
    # ===========================================================================
    # BOARDS & PANELS (MDF, Laminated) - NEW
    # ===========================================================================
    {"code": "BOARD_MDF_WHITE", "name": "MDF Board White (8x4ft)", "category": "board", "unit": "board", "default_price": Decimal("45000")},
    {"code": "BOARD_MDF_BLACK", "name": "MDF Board Black (8x4ft)", "category": "board", "unit": "board", "default_price": Decimal("48000")},
    {"code": "BOARD_MDF_NAVY", "name": "MDF Board Navy (8x4ft)", "category": "board", "unit": "board", "default_price": Decimal("48000")},
    {"code": "BOARD_MDF_VINTAGE", "name": "MDF Board Vintage/Wood (8x4ft)", "category": "board", "unit": "board", "default_price": Decimal("52000")},
    {"code": "BOARD_MDF_GREY", "name": "MDF Board Grey (8x4ft)", "category": "board", "unit": "board", "default_price": Decimal("48000")},
    {"code": "BOARD_MDF_PLAIN", "name": "MDF Board Plain (8x4ft)", "category": "board", "unit": "board", "default_price": Decimal("35000")},
    {"code": "BOARD_PLY_12MM", "name": "Plywood 12mm (8x4ft)", "category": "board", "unit": "board", "default_price": Decimal("42000")},
    {"code": "BOARD_PLY_18MM", "name": "Plywood 18mm (8x4ft)", "category": "board", "unit": "board", "default_price": Decimal("55000")},
    
    # ===========================================================================
    # ALUMINUM PROFILES/FRAMES - NEW
    # ===========================================================================
    {"code": "ALU_WINDOW_FRAME", "name": "Aluminum Window Frame Profile (6m)", "category": "aluminum", "unit": "length_6m", "default_price": Decimal("25000")},
    {"code": "ALU_SLIDING_TRACK", "name": "Aluminum Sliding Track (6m)", "category": "aluminum", "unit": "length_6m", "default_price": Decimal("18000")},
    {"code": "ALU_ANGLE_25x25", "name": "Aluminum Angle 25x25mm (6m)", "category": "aluminum", "unit": "length_6m", "default_price": Decimal("15000")},
    {"code": "ALU_CHANNEL_U", "name": "Aluminum U-Channel (6m)", "category": "aluminum", "unit": "length_6m", "default_price": Decimal("22000")},
    {"code": "ALU_FLAT_25x3", "name": "Aluminum Flat Bar 25x3mm (6m)", "category": "aluminum", "unit": "length_6m", "default_price": Decimal("12000")},
    
    # ===========================================================================
    # ELECTRODES (separated from consumables)
    # ===========================================================================
    {"code": "ELECTRODE_2.5_PKT", "name": "Electrodes 2.5mm (packet)", "category": "electrode", "unit": "packet", "default_price": Decimal("3500")},
    {"code": "ELECTRODE_3.2_PKT", "name": "Electrodes 3.2mm (packet)", "category": "electrode", "unit": "packet", "default_price": Decimal("4000")},
    {"code": "ELECTRODE_4.0_PKT", "name": "Electrodes 4.0mm (packet)", "category": "electrode", "unit": "packet", "default_price": Decimal("4500")},
    {"code": "WELDING_WIRE_0.8", "name": "MIG Welding Wire 0.8mm (5kg)", "category": "electrode", "unit": "piece", "default_price": Decimal("18000")},
    {"code": "WELDING_WIRE_1.0", "name": "MIG Welding Wire 1.0mm (5kg)", "category": "electrode", "unit": "piece", "default_price": Decimal("20000")},
    
    # ===========================================================================
    # DISCS - CUTTING/GRINDING (separated)
    # ===========================================================================
    {"code": "DISC_CUT_4IN", "name": "Cutting Disc 4in (100mm)", "category": "disc", "unit": "piece", "default_price": Decimal("1500")},
    {"code": "DISC_CUT_7IN", "name": "Cutting Disc 7in (180mm)", "category": "disc", "unit": "piece", "default_price": Decimal("3500")},
    {"code": "DISC_CUT_9IN", "name": "Cutting Disc 9in (230mm)", "category": "disc", "unit": "piece", "default_price": Decimal("4500")},
    {"code": "DISC_GRIND_4IN", "name": "Grinding Disc 4in", "category": "disc", "unit": "piece", "default_price": Decimal("2000")},
    {"code": "DISC_GRIND_7IN", "name": "Grinding Disc 7in", "category": "disc", "unit": "piece", "default_price": Decimal("4000")},
    {"code": "DISC_FLAP_4IN", "name": "Flap Disc 4in", "category": "disc", "unit": "piece", "default_price": Decimal("3000")},
    {"code": "DISC_FLAP_7IN", "name": "Flap Disc 7in", "category": "disc", "unit": "piece", "default_price": Decimal("5500")},
    
    # ===========================================================================
    # SANDING DISCS - NEW (separated)
    # ===========================================================================
    {"code": "DISC_SAND_4IN_40", "name": "Sanding Disc 4in (40 grit)", "category": "sanding", "unit": "piece", "default_price": Decimal("800")},
    {"code": "DISC_SAND_4IN_80", "name": "Sanding Disc 4in (80 grit)", "category": "sanding", "unit": "piece", "default_price": Decimal("800")},
    {"code": "DISC_SAND_4IN_120", "name": "Sanding Disc 4in (120 grit)", "category": "sanding", "unit": "piece", "default_price": Decimal("800")},
    {"code": "DISC_SAND_7IN_40", "name": "Sanding Disc 7in (40 grit)", "category": "sanding", "unit": "piece", "default_price": Decimal("1500")},
    {"code": "DISC_SAND_7IN_80", "name": "Sanding Disc 7in (80 grit)", "category": "sanding", "unit": "piece", "default_price": Decimal("1500")},
    {"code": "SANDPAPER_SHEET", "name": "Sandpaper Sheet (Assorted)", "category": "sanding", "unit": "piece", "default_price": Decimal("300")},
    
    # ===========================================================================
    # PAINT & FINISHES
    # ===========================================================================
    {"code": "PAINT_GLOSS_5L", "name": "Gloss Paint 5L", "category": "paint", "unit": "piece", "default_price": Decimal("18000")},
    {"code": "PAINT_GLOSS_1L", "name": "Gloss Paint 1L", "category": "paint", "unit": "piece", "default_price": Decimal("5000")},
    {"code": "PAINT_LITRE", "name": "Paint (per litre)", "category": "paint", "unit": "litre", "default_price": Decimal("5500")},
    {"code": "RED_OXIDE_5L", "name": "Red Oxide Primer 5L", "category": "paint", "unit": "piece", "default_price": Decimal("12000")},
    {"code": "RED_OXIDE_1L", "name": "Red Oxide Primer 1L", "category": "paint", "unit": "piece", "default_price": Decimal("3500")},
    {"code": "PRIMER_5L", "name": "Primer 5L", "category": "paint", "unit": "piece", "default_price": Decimal("14000")},
    {"code": "PRIMER_1L", "name": "Primer 1L", "category": "paint", "unit": "piece", "default_price": Decimal("4000")},
    {"code": "VARNISH_5L", "name": "Varnish 5L", "category": "paint", "unit": "piece", "default_price": Decimal("22000")},
    {"code": "VARNISH_1L", "name": "Varnish 1L", "category": "paint", "unit": "piece", "default_price": Decimal("6000")},
    {"code": "THINNER_5L", "name": "Paint Thinner 5L", "category": "paint", "unit": "piece", "default_price": Decimal("8000")},
    {"code": "THINNER_1L", "name": "Paint Thinner 1L", "category": "paint", "unit": "piece", "default_price": Decimal("2500")},
    {"code": "LACQUER_SPRAY", "name": "Lacquer Spray Can", "category": "paint", "unit": "piece", "default_price": Decimal("3500")},
    
    # ===========================================================================
    # HARDWARE
    # ===========================================================================
    {"code": "HINGE_3IN", "name": "Hinge 3in (pair)", "category": "hardware", "unit": "piece", "default_price": Decimal("2500")},
    {"code": "HINGE_4IN", "name": "Hinge 4in (pair)", "category": "hardware", "unit": "piece", "default_price": Decimal("3500")},
    {"code": "HINGE_5IN", "name": "Hinge 5in (pair)", "category": "hardware", "unit": "piece", "default_price": Decimal("4500")},
    {"code": "LOCK_PADLOCK", "name": "Padlock Hasp & Staple", "category": "hardware", "unit": "piece", "default_price": Decimal("4000")},
    {"code": "LOCK_MORTISE", "name": "Mortise Lock Set", "category": "hardware", "unit": "piece", "default_price": Decimal("15000")},
    {"code": "LOCK_RIM", "name": "Rim Lock Set", "category": "hardware", "unit": "piece", "default_price": Decimal("12000")},
    {"code": "HANDLE_DOOR", "name": "Door Handle", "category": "hardware", "unit": "piece", "default_price": Decimal("8000")},
    {"code": "HANDLE_WINDOW", "name": "Window Handle", "category": "hardware", "unit": "piece", "default_price": Decimal("3500")},
    {"code": "BOLT_M6_PKT", "name": "Bolts M6 (packet of 10)", "category": "hardware", "unit": "packet", "default_price": Decimal("1200")},
    {"code": "BOLT_M8_PKT", "name": "Bolts M8 (packet of 10)", "category": "hardware", "unit": "packet", "default_price": Decimal("1500")},
    {"code": "BOLT_M10_PKT", "name": "Bolts M10 (packet of 10)", "category": "hardware", "unit": "packet", "default_price": Decimal("2000")},
    {"code": "BOLT_M12_PKT", "name": "Bolts M12 (packet of 10)", "category": "hardware", "unit": "packet", "default_price": Decimal("2500")},
    {"code": "NUT_M8_PKT", "name": "Nuts M8 (packet of 20)", "category": "hardware", "unit": "packet", "default_price": Decimal("800")},
    {"code": "WASHER_PKT", "name": "Washers (packet of 50)", "category": "hardware", "unit": "packet", "default_price": Decimal("600")},
    {"code": "CASTER_WHEEL", "name": "Caster Wheel", "category": "hardware", "unit": "piece", "default_price": Decimal("3500")},
    {"code": "CASTER_WHEEL_HD", "name": "Caster Wheel Heavy Duty", "category": "hardware", "unit": "piece", "default_price": Decimal("6000")},
    {"code": "GATE_WHEEL", "name": "Gate Wheel (V-groove)", "category": "hardware", "unit": "piece", "default_price": Decimal("8000")},
    {"code": "DOOR_CLOSER", "name": "Door Closer", "category": "hardware", "unit": "piece", "default_price": Decimal("18000")},
    {"code": "TOWER_BOLT", "name": "Tower Bolt 6in", "category": "hardware", "unit": "piece", "default_price": Decimal("2000")},
]


# ==============================================================================
# DEFAULT TEMPLATES
# ==============================================================================

DEFAULT_TEMPLATES: List[Dict[str, Any]] = [
    # ===========================================================================
    # BED FRAMES
    # ===========================================================================
    {
        "code": "BED_3x4",
        "name": "Bed Frame 3ft x 4ft (Single)",
        "params_schema": {"width_ft": 3, "length_ft": 4},
        "base_bom": {
            "TUBE_40x40": {"qty_formula": "frame_perimeter", "base_qty": 2},
            "FLAT_25x3": {"qty_formula": "slats", "base_qty": 0.5},
            "RED_OXIDE_1L": {"qty_formula": "fixed", "base_qty": 1},
            "PAINT_GLOSS_1L": {"qty_formula": "fixed", "base_qty": 1},
            "ELECTRODE_2.5_PKT": {"qty_formula": "fixed", "base_qty": 0.5},
        },
        "default_labour_hours": Decimal("3"),
    },
    {
        "code": "BED_4x6",
        "name": "Bed Frame 4ft x 6ft (Double)",
        "params_schema": {"width_ft": 4, "length_ft": 6},
        "base_bom": {
            "TUBE_40x40": {"qty_formula": "frame_perimeter", "base_qty": 3},
            "FLAT_25x3": {"qty_formula": "slats", "base_qty": 1},
            "RED_OXIDE_5L": {"qty_formula": "fixed", "base_qty": 0.5},
            "PAINT_GLOSS_5L": {"qty_formula": "fixed", "base_qty": 0.5},
            "ELECTRODE_2.5_PKT": {"qty_formula": "fixed", "base_qty": 1},
            "DISC_CUT_4IN": {"qty_formula": "fixed", "base_qty": 1},
        },
        "default_labour_hours": Decimal("4"),
    },
    {
        "code": "BED_5x6",
        "name": "Bed Frame 5ft x 6ft (Queen)",
        "params_schema": {"width_ft": 5, "length_ft": 6},
        "base_bom": {
            "TUBE_50x50": {"qty_formula": "frame_perimeter", "base_qty": 3},
            "TUBE_40x40": {"qty_formula": "supports", "base_qty": 1},
            "FLAT_25x3": {"qty_formula": "slats", "base_qty": 1.5},
            "RED_OXIDE_5L": {"qty_formula": "fixed", "base_qty": 0.5},
            "PAINT_GLOSS_5L": {"qty_formula": "fixed", "base_qty": 0.5},
            "ELECTRODE_3.2_PKT": {"qty_formula": "fixed", "base_qty": 1},
            "DISC_CUT_4IN": {"qty_formula": "fixed", "base_qty": 2},
        },
        "default_labour_hours": Decimal("5"),
    },
    {
        "code": "BED_6x6",
        "name": "Bed Frame 6ft x 6ft (King)",
        "params_schema": {"width_ft": 6, "length_ft": 6},
        "base_bom": {
            "TUBE_50x50": {"qty_formula": "frame_perimeter", "base_qty": 4},
            "TUBE_40x40": {"qty_formula": "supports", "base_qty": 2},
            "FLAT_25x3": {"qty_formula": "slats", "base_qty": 2},
            "RED_OXIDE_5L": {"qty_formula": "fixed", "base_qty": 0.7},
            "PAINT_GLOSS_5L": {"qty_formula": "fixed", "base_qty": 0.7},
            "ELECTRODE_3.2_PKT": {"qty_formula": "fixed", "base_qty": 1.5},
            "DISC_CUT_4IN": {"qty_formula": "fixed", "base_qty": 3},
        },
        "default_labour_hours": Decimal("6"),
    },
    # ===========================================================================
    # TV STANDS
    # ===========================================================================
    {
        "code": "TV_STAND_BASIC",
        "name": "TV Stand (Basic 1.0m)",
        "params_schema": {"width_m": 1.0, "height_m": 0.45, "depth_m": 0.35},
        "base_bom": {
            "TUBE_20x20": {"qty_formula": "frame", "base_qty": 1.5},
            "BOARD_MDF_PLAIN": {"qty_formula": "shelves", "base_qty": 0.25},
            "RED_OXIDE_1L": {"qty_formula": "fixed", "base_qty": 0.3},
            "PAINT_GLOSS_1L": {"qty_formula": "fixed", "base_qty": 0.3},
            "ELECTRODE_2.5_PKT": {"qty_formula": "fixed", "base_qty": 0.3},
            "CASTER_WHEEL": {"qty_formula": "fixed", "base_qty": 4},
        },
        "default_labour_hours": Decimal("2"),
    },
    {
        "code": "TV_STAND_PREMIUM",
        "name": "TV Stand (Premium 1.5m)",
        "params_schema": {"width_m": 1.5, "height_m": 0.55, "depth_m": 0.4},
        "base_bom": {
            "TUBE_25x25": {"qty_formula": "frame", "base_qty": 2.5},
            "BOARD_MDF_BLACK": {"qty_formula": "shelves", "base_qty": 0.5},
            "RED_OXIDE_1L": {"qty_formula": "fixed", "base_qty": 0.5},
            "PAINT_GLOSS_1L": {"qty_formula": "fixed", "base_qty": 0.5},
            "ELECTRODE_2.5_PKT": {"qty_formula": "fixed", "base_qty": 0.5},
            "CASTER_WHEEL": {"qty_formula": "fixed", "base_qty": 4},
        },
        "default_labour_hours": Decimal("3.5"),
    },
    {
        "code": "TV_STAND_WALL",
        "name": "TV Stand Wall Mount Console (1.8m)",
        "params_schema": {"width_m": 1.8, "height_m": 0.35, "depth_m": 0.3},
        "base_bom": {
            "TUBE_25x25": {"qty_formula": "frame", "base_qty": 2},
            "BOARD_MDF_WHITE": {"qty_formula": "shelves", "base_qty": 0.5},
            "FLAT_25x3": {"qty_formula": "brackets", "base_qty": 0.5},
            "RED_OXIDE_1L": {"qty_formula": "fixed", "base_qty": 0.3},
            "PAINT_GLOSS_1L": {"qty_formula": "fixed", "base_qty": 0.3},
            "ELECTRODE_2.5_PKT": {"qty_formula": "fixed", "base_qty": 0.3},
        },
        "default_labour_hours": Decimal("3"),
    },
    # ===========================================================================
    # WINDOWS
    # ===========================================================================
    {
        "code": "WINDOW_0.9x1.0",
        "name": "Window Frame (0.9m x 1.0m)",
        "params_schema": {"width_m": 0.9, "height_m": 1.0},
        "base_bom": {
            "TUBE_25x25": {"qty_formula": "frame_perimeter", "base_qty": 1},
            "TUBE_20x20": {"qty_formula": "dividers", "base_qty": 0.5},
            "RED_OXIDE_1L": {"qty_formula": "fixed", "base_qty": 0.3},
            "PAINT_GLOSS_1L": {"qty_formula": "fixed", "base_qty": 0.3},
            "ELECTRODE_2.5_PKT": {"qty_formula": "fixed", "base_qty": 0.3},
        },
        "default_labour_hours": Decimal("2"),
    },
    {
        "code": "WINDOW_1.2x1.2",
        "name": "Sliding Window Frame (1.2m x 1.2m)",
        "params_schema": {"width_m": 1.2, "height_m": 1.2},
        "base_bom": {
            "TUBE_25x25": {"qty_formula": "frame_perimeter", "base_qty": 1.5},
            "FLAT_25x3": {"qty_formula": "tracks", "base_qty": 0.5},
            "HANDLE_WINDOW": {"qty_formula": "fixed", "base_qty": 2},
            "RED_OXIDE_1L": {"qty_formula": "fixed", "base_qty": 0.5},
            "PAINT_GLOSS_1L": {"qty_formula": "fixed", "base_qty": 0.5},
            "ELECTRODE_2.5_PKT": {"qty_formula": "fixed", "base_qty": 0.3},
        },
        "default_labour_hours": Decimal("3"),
    },
    {
        "code": "WINDOW_1.5x1.2",
        "name": "Sliding Window Frame (1.5m x 1.2m)",
        "params_schema": {"width_m": 1.5, "height_m": 1.2},
        "base_bom": {
            "TUBE_25x25": {"qty_formula": "frame_perimeter", "base_qty": 2},
            "FLAT_25x3": {"qty_formula": "tracks", "base_qty": 0.7},
            "HANDLE_WINDOW": {"qty_formula": "fixed", "base_qty": 2},
            "RED_OXIDE_1L": {"qty_formula": "fixed", "base_qty": 0.5},
            "PAINT_GLOSS_1L": {"qty_formula": "fixed", "base_qty": 0.5},
            "ELECTRODE_2.5_PKT": {"qty_formula": "fixed", "base_qty": 0.5},
        },
        "default_labour_hours": Decimal("3.5"),
    },
    {
        "code": "WINDOW_1.8x1.5",
        "name": "Large Sliding Window (1.8m x 1.5m)",
        "params_schema": {"width_m": 1.8, "height_m": 1.5},
        "base_bom": {
            "TUBE_30x30": {"qty_formula": "frame_perimeter", "base_qty": 2.5},
            "TUBE_25x25": {"qty_formula": "panels", "base_qty": 1},
            "FLAT_25x3": {"qty_formula": "tracks", "base_qty": 1},
            "HANDLE_WINDOW": {"qty_formula": "fixed", "base_qty": 2},
            "RED_OXIDE_1L": {"qty_formula": "fixed", "base_qty": 0.7},
            "PAINT_GLOSS_5L": {"qty_formula": "fixed", "base_qty": 0.3},
            "ELECTRODE_2.5_PKT": {"qty_formula": "fixed", "base_qty": 0.7},
        },
        "default_labour_hours": Decimal("4.5"),
    },
    # ===========================================================================
    # DOORS
    # ===========================================================================
    {
        "code": "DOOR_0.9x2.1",
        "name": "Security Door (0.9m x 2.1m)",
        "params_schema": {"width_m": 0.9, "height_m": 2.1},
        "base_bom": {
            "TUBE_40x40": {"qty_formula": "frame", "base_qty": 2},
            "TUBE_25x25": {"qty_formula": "infill", "base_qty": 2},
            "SHEET_1.0": {"qty_formula": "panel", "base_qty": 0.5},
            "HINGE_4IN": {"qty_formula": "fixed", "base_qty": 3},
            "LOCK_MORTISE": {"qty_formula": "fixed", "base_qty": 1},
            "HANDLE_DOOR": {"qty_formula": "fixed", "base_qty": 1},
            "RED_OXIDE_5L": {"qty_formula": "fixed", "base_qty": 0.5},
            "PAINT_GLOSS_5L": {"qty_formula": "fixed", "base_qty": 0.5},
            "ELECTRODE_2.5_PKT": {"qty_formula": "fixed", "base_qty": 1},
            "DISC_CUT_4IN": {"qty_formula": "fixed", "base_qty": 2},
        },
        "default_labour_hours": Decimal("6"),
    },
    {
        "code": "DOOR_1.0x2.1",
        "name": "Security Door (1.0m x 2.1m)",
        "params_schema": {"width_m": 1.0, "height_m": 2.1},
        "base_bom": {
            "TUBE_40x40": {"qty_formula": "frame", "base_qty": 2.5},
            "TUBE_25x25": {"qty_formula": "infill", "base_qty": 2.5},
            "SHEET_1.0": {"qty_formula": "panel", "base_qty": 0.6},
            "HINGE_5IN": {"qty_formula": "fixed", "base_qty": 3},
            "LOCK_MORTISE": {"qty_formula": "fixed", "base_qty": 1},
            "HANDLE_DOOR": {"qty_formula": "fixed", "base_qty": 1},
            "TOWER_BOLT": {"qty_formula": "fixed", "base_qty": 2},
            "RED_OXIDE_5L": {"qty_formula": "fixed", "base_qty": 0.6},
            "PAINT_GLOSS_5L": {"qty_formula": "fixed", "base_qty": 0.6},
            "ELECTRODE_2.5_PKT": {"qty_formula": "fixed", "base_qty": 1.2},
            "DISC_CUT_4IN": {"qty_formula": "fixed", "base_qty": 3},
        },
        "default_labour_hours": Decimal("7"),
    },
    {
        "code": "DOOR_DOUBLE",
        "name": "Double Security Door (1.8m x 2.1m)",
        "params_schema": {"width_m": 1.8, "height_m": 2.1},
        "base_bom": {
            "TUBE_50x50": {"qty_formula": "frame", "base_qty": 3},
            "TUBE_40x40": {"qty_formula": "panels", "base_qty": 3},
            "TUBE_25x25": {"qty_formula": "infill", "base_qty": 4},
            "SHEET_1.2": {"qty_formula": "panel", "base_qty": 1},
            "HINGE_5IN": {"qty_formula": "fixed", "base_qty": 6},
            "LOCK_MORTISE": {"qty_formula": "fixed", "base_qty": 2},
            "HANDLE_DOOR": {"qty_formula": "fixed", "base_qty": 2},
            "TOWER_BOLT": {"qty_formula": "fixed", "base_qty": 4},
            "RED_OXIDE_5L": {"qty_formula": "fixed", "base_qty": 1},
            "PAINT_GLOSS_5L": {"qty_formula": "fixed", "base_qty": 1},
            "ELECTRODE_3.2_PKT": {"qty_formula": "fixed", "base_qty": 2},
            "DISC_CUT_4IN": {"qty_formula": "fixed", "base_qty": 5},
        },
        "default_labour_hours": Decimal("12"),
    },
    # ===========================================================================
    # GATES
    # ===========================================================================
    {
        "code": "GATE_SWING_1.2",
        "name": "Swing Gate (1.2m x 1.5m)",
        "params_schema": {"width_m": 1.2, "height_m": 1.5},
        "base_bom": {
            "TUBE_40x40": {"qty_formula": "frame", "base_qty": 2},
            "TUBE_25x25": {"qty_formula": "infill", "base_qty": 2},
            "FLAT_25x3": {"qty_formula": "decorative", "base_qty": 0.5},
            "HINGE_5IN": {"qty_formula": "fixed", "base_qty": 3},
            "LOCK_PADLOCK": {"qty_formula": "fixed", "base_qty": 1},
            "RED_OXIDE_5L": {"qty_formula": "fixed", "base_qty": 0.5},
            "PAINT_GLOSS_5L": {"qty_formula": "fixed", "base_qty": 0.5},
            "ELECTRODE_2.5_PKT": {"qty_formula": "fixed", "base_qty": 1},
            "DISC_CUT_4IN": {"qty_formula": "fixed", "base_qty": 2},
        },
        "default_labour_hours": Decimal("5"),
    },
    {
        "code": "GATE_SLIDING_3x1.8",
        "name": "Sliding Gate (3m x 1.8m)",
        "params_schema": {"width_m": 3, "height_m": 1.8},
        "base_bom": {
            "TUBE_50x50": {"qty_formula": "frame", "base_qty": 4},
            "TUBE_40x40": {"qty_formula": "infill", "base_qty": 4},
            "TUBE_25x25": {"qty_formula": "decorative", "base_qty": 2},
            "ANGLE_40x40": {"qty_formula": "tracks", "base_qty": 1},
            "GATE_WHEEL": {"qty_formula": "fixed", "base_qty": 2},
            "RED_OXIDE_5L": {"qty_formula": "fixed", "base_qty": 1},
            "PAINT_GLOSS_5L": {"qty_formula": "fixed", "base_qty": 1},
            "ELECTRODE_3.2_PKT": {"qty_formula": "fixed", "base_qty": 2},
            "DISC_CUT_4IN": {"qty_formula": "fixed", "base_qty": 4},
        },
        "default_labour_hours": Decimal("8"),
    },
    {
        "code": "GATE_SLIDING_4x2",
        "name": "Sliding Gate (4m x 2m)",
        "params_schema": {"width_m": 4, "height_m": 2},
        "base_bom": {
            "TUBE_60x60": {"qty_formula": "frame", "base_qty": 5},
            "TUBE_50x50": {"qty_formula": "supports", "base_qty": 2},
            "TUBE_40x40": {"qty_formula": "infill", "base_qty": 5},
            "TUBE_25x25": {"qty_formula": "decorative", "base_qty": 3},
            "ANGLE_50x50": {"qty_formula": "tracks", "base_qty": 1.5},
            "GATE_WHEEL": {"qty_formula": "fixed", "base_qty": 3},
            "RED_OXIDE_5L": {"qty_formula": "fixed", "base_qty": 1.5},
            "PAINT_GLOSS_5L": {"qty_formula": "fixed", "base_qty": 1.5},
            "ELECTRODE_3.2_PKT": {"qty_formula": "fixed", "base_qty": 3},
            "DISC_CUT_4IN": {"qty_formula": "fixed", "base_qty": 5},
        },
        "default_labour_hours": Decimal("12"),
    },
    # ===========================================================================
    # BURGLAR BARS
    # ===========================================================================
    {
        "code": "BURGLAR_FIXED",
        "name": "Burglar Bars Fixed (1.2m x 1.2m)",
        "params_schema": {"width_m": 1.2, "height_m": 1.2},
        "base_bom": {
            "TUBE_20x20": {"qty_formula": "bars", "base_qty": 2},
            "FLAT_25x3": {"qty_formula": "frame", "base_qty": 1},
            "RED_OXIDE_1L": {"qty_formula": "fixed", "base_qty": 0.3},
            "PAINT_GLOSS_1L": {"qty_formula": "fixed", "base_qty": 0.3},
            "ELECTRODE_2.5_PKT": {"qty_formula": "fixed", "base_qty": 0.5},
        },
        "default_labour_hours": Decimal("2"),
    },
    {
        "code": "BURGLAR_EXPANDABLE",
        "name": "Burglar Gate Expandable (1m x 2m)",
        "params_schema": {"width_m": 1.0, "height_m": 2.0},
        "base_bom": {
            "FLAT_25x3": {"qty_formula": "lattice", "base_qty": 4},
            "TUBE_25x25": {"qty_formula": "frame", "base_qty": 1.5},
            "HINGE_4IN": {"qty_formula": "fixed", "base_qty": 2},
            "LOCK_PADLOCK": {"qty_formula": "fixed", "base_qty": 1},
            "RED_OXIDE_1L": {"qty_formula": "fixed", "base_qty": 0.5},
            "PAINT_GLOSS_1L": {"qty_formula": "fixed", "base_qty": 0.5},
            "ELECTRODE_2.5_PKT": {"qty_formula": "fixed", "base_qty": 1},
        },
        "default_labour_hours": Decimal("4"),
    },
    # ===========================================================================
    # SHELVING & RACKS
    # ===========================================================================
    {
        "code": "SHELF_WALL",
        "name": "Wall Shelf Bracket Set (0.6m)",
        "params_schema": {"width_m": 0.6},
        "base_bom": {
            "FLAT_25x3": {"qty_formula": "brackets", "base_qty": 0.5},
            "TUBE_20x20": {"qty_formula": "frame", "base_qty": 0.3},
            "ELECTRODE_2.5_PKT": {"qty_formula": "fixed", "base_qty": 0.2},
        },
        "default_labour_hours": Decimal("1"),
    },
    {
        "code": "RACK_STORAGE",
        "name": "Storage Rack 4-Tier (1.2m x 1.8m)",
        "params_schema": {"width_m": 1.2, "height_m": 1.8, "depth_m": 0.45},
        "base_bom": {
            "ANGLE_40x40": {"qty_formula": "uprights", "base_qty": 3},
            "ANGLE_25x25": {"qty_formula": "shelves", "base_qty": 2},
            "BOARD_PLY_12MM": {"qty_formula": "shelves", "base_qty": 0.5},
            "BOLT_M8_PKT": {"qty_formula": "fixed", "base_qty": 2},
            "RED_OXIDE_1L": {"qty_formula": "fixed", "base_qty": 0.5},
            "ELECTRODE_2.5_PKT": {"qty_formula": "fixed", "base_qty": 0.5},
        },
        "default_labour_hours": Decimal("3"),
    },
]


# ==============================================================================
# CORE COMPUTATION FUNCTIONS (PURE, DETERMINISTIC)
# ==============================================================================


def get_default_materials() -> List[Dict[str, Any]]:
    """Return the default materials catalog."""
    return DEFAULT_MATERIALS.copy()


def get_default_templates() -> List[Dict[str, Any]]:
    """Return the default product templates."""
    return DEFAULT_TEMPLATES.copy()


def seed_default_materials(
    existing_codes: List[str],
) -> List[Dict[str, Any]]:
    """
    Determine which default materials need to be seeded.
    
    Args:
        existing_codes: List of material codes already in the database
    
    Returns:
        List of material dicts to create (only those not already existing)
    
    This is a pure function that determines WHAT to seed.
    Actual creation is done by the caller.
    """
    existing_set = set(existing_codes)
    to_seed = []
    
    for mat in DEFAULT_MATERIALS:
        if mat["code"] not in existing_set:
            to_seed.append(mat.copy())
    
    return to_seed


def estimate_bom(
    template_code: str,
    specs: Dict[str, Any],
    tuning: Optional[TuningData],
    materials_catalog: Dict[str, MaterialData],
    templates: Optional[Dict[str, Dict]] = None,
) -> EstimationResult:
    """
    Estimate Bill of Materials for a product based on template and specs.
    
    Args:
        template_code: Template identifier (e.g., "BED_4x6")
        specs: User-provided specifications (dimensions, etc.)
        tuning: Optional tuning multipliers for this template
        materials_catalog: Map of material code -> MaterialData
        templates: Optional template definitions (uses defaults if not provided)
    
    Returns:
        EstimationResult with BOM items and cut list info
    
    Pure function: deterministic output for same inputs.
    """
    # Find template
    if templates is None:
        templates = {t["code"]: t for t in DEFAULT_TEMPLATES}
    
    template = templates.get(template_code)
    if template is None:
        # Return empty result for unknown template
        return EstimationResult(
            bom=[],
            total_tube_length_m=Decimal("0"),
            recommended_6m_lengths=0,
            wastage_factor=Decimal("1.0"),
            cut_list_notes="Unknown template",
        )
    
    # Get tuning multipliers (default to 1.0 if not provided)
    tube_mult = Decimal(tuning["tube_multiplier"]) if tuning else Decimal("1.0")
    paint_mult = Decimal(tuning["paint_multiplier"]) if tuning else Decimal("1.0")
    consumable_mult = Decimal(tuning["consumable_multiplier"]) if tuning else Decimal("1.0")
    
    base_bom = template.get("base_bom", {})
    bom_items: List[BOMItem] = []
    total_tube_length_m = Decimal("0")
    
    for mat_code, bom_spec in base_bom.items():
        material = materials_catalog.get(mat_code)
        if material is None:
            continue
        
        base_qty = Decimal(str(bom_spec.get("base_qty", 1)))
        
        # Apply category-specific tuning multiplier
        category = material["category"]
        if category == "tube":
            qty = base_qty * tube_mult
            # Track tube length for cut list (handle both 5.8m and 6m)
            if material["unit"] == "length_6m":
                total_tube_length_m += qty * Decimal("6")
            elif material["unit"] == "length_5_8m":
                total_tube_length_m += qty * Decimal("5.8")
        elif category in ("paint", "finish"):
            qty = base_qty * paint_mult
        elif category in ("consumable", "electrode", "disc", "sanding"):
            qty = base_qty * consumable_mult
        else:
            qty = base_qty
        
        # Round up to reasonable precision
        qty = qty.quantize(Decimal("0.01"))
        
        unit_price = material["price_mwk"]
        line_total = qty * unit_price
        
        bom_items.append(BOMItem(
            material_code=mat_code,
            material_name=material["name"],
            category=category,
            quantity=qty,
            unit=material["unit"],
            unit_price_mwk=unit_price,
            line_total_mwk=line_total,
        ))
    
    # Calculate cut list recommendations
    wastage_factor = Decimal("1.10")  # 10% wastage default
    total_with_wastage = total_tube_length_m * wastage_factor
    recommended_6m = int((total_with_wastage / Decimal("6")).to_integral_value()) + 1
    
    cut_list_notes = (
        f"Total tube length required: {total_tube_length_m:.1f}m. "
        f"With 10% wastage allowance: {total_with_wastage:.1f}m. "
        f"Recommended: {recommended_6m} x 6m lengths."
    )
    
    return EstimationResult(
        bom=bom_items,
        total_tube_length_m=total_tube_length_m,
        recommended_6m_lengths=recommended_6m,
        wastage_factor=wastage_factor,
        cut_list_notes=cut_list_notes,
    )


def compute_cost(
    bom_items: List[BOMItem],
    labour_hours: Decimal,
    labour_rate_per_hour: Decimal,
    overhead_pct: Decimal,
    margin_pct: Decimal,
) -> CostBreakdown:
    """
    Compute total cost and pricing from BOM and labour.
    
    Args:
        bom_items: List of BOM items with quantities and prices
        labour_hours: Estimated labour hours
        labour_rate_per_hour: Labour cost per hour in MWK
        overhead_pct: Overhead/wastage percentage (e.g., 10 for 10%)
        margin_pct: Profit margin percentage (e.g., 25 for 25%)
    
    Returns:
        CostBreakdown with all cost components and recommended pricing
    
    Pure function: deterministic output for same inputs.
    """
    # Materials cost
    materials_cost = sum((item["line_total_mwk"] for item in bom_items), Decimal("0"))
    
    # Labour cost
    labour_cost = labour_hours * labour_rate_per_hour
    
    # Overhead
    subtotal_before_overhead = materials_cost + labour_cost
    overhead_cost = subtotal_before_overhead * (overhead_pct / Decimal("100"))
    
    # Subtotal before margin
    subtotal_before_margin = subtotal_before_overhead + overhead_cost
    
    # Margin
    margin_amount = subtotal_before_margin * (margin_pct / Decimal("100"))
    
    # Total (recommended price)
    total = subtotal_before_margin + margin_amount
    
    # Min price (break-even = just cover costs + overhead)
    min_price = subtotal_before_margin
    
    return CostBreakdown(
        materials_cost=materials_cost,
        labour_cost=labour_cost,
        overhead_cost=overhead_cost,
        subtotal_before_margin=subtotal_before_margin,
        margin_amount=margin_amount,
        total=total,
        min_price=min_price,
    )


def update_tuning(
    previous_tuning: TuningData,
    estimated_bom: List[BOMItem],
    actual_bom: List[BOMItem],
    estimated_labour: Decimal,
    actual_labour: Decimal,
    learning_rate: Decimal = Decimal("0.1"),
    min_multiplier: Decimal = Decimal("0.5"),
    max_multiplier: Decimal = Decimal("2.0"),
) -> TuningData:
    """
    Update tuning multipliers based on actual vs estimated usage.
    
    Uses bounded moving average to prevent wild swings.
    
    Args:
        previous_tuning: Current tuning multipliers
        estimated_bom: BOM from the estimate
        actual_bom: Actual materials used
        estimated_labour: Estimated labour hours
        actual_labour: Actual labour hours
        learning_rate: How quickly to adjust (0.1 = 10% weight to new data)
        min_multiplier: Minimum allowed multiplier
        max_multiplier: Maximum allowed multiplier
    
    Returns:
        Updated TuningData
    
    Pure function: deterministic output for same inputs.
    """
    def _sum_by_category(bom: List[BOMItem], category: str) -> Decimal:
        return sum(
            (item["quantity"] for item in bom if item["category"] == category),
            Decimal("0"),
        )
    
    def _update_multiplier(
        prev_mult: Decimal,
        estimated: Decimal,
        actual: Decimal,
    ) -> Decimal:
        """Calculate new multiplier using bounded moving average."""
        if estimated == 0:
            return prev_mult
        
        # Ratio of actual to estimated
        ratio = actual / estimated
        
        # Apply learning rate (weighted average)
        new_mult = prev_mult * (1 - learning_rate) + (prev_mult * ratio) * learning_rate
        
        # Bound the result
        return max(min_multiplier, min(max_multiplier, new_mult))
    
    # Calculate category totals
    est_tube = _sum_by_category(estimated_bom, "tube")
    act_tube = _sum_by_category(actual_bom, "tube")
    
    est_paint = _sum_by_category(estimated_bom, "paint")
    act_paint = _sum_by_category(actual_bom, "paint")
    
    est_consumable = _sum_by_category(estimated_bom, "consumable")
    act_consumable = _sum_by_category(actual_bom, "consumable")
    
    # Update each multiplier
    new_tube_mult = _update_multiplier(
        previous_tuning["tube_multiplier"],
        est_tube,
        act_tube,
    )
    new_paint_mult = _update_multiplier(
        previous_tuning["paint_multiplier"],
        est_paint,
        act_paint,
    )
    new_consumable_mult = _update_multiplier(
        previous_tuning["consumable_multiplier"],
        est_consumable,
        act_consumable,
    )
    new_labour_mult = _update_multiplier(
        previous_tuning["labour_multiplier"],
        estimated_labour,
        actual_labour,
    )
    
    return TuningData(
        tube_multiplier=new_tube_mult.quantize(Decimal("0.01")),
        paint_multiplier=new_paint_mult.quantize(Decimal("0.01")),
        consumable_multiplier=new_consumable_mult.quantize(Decimal("0.01")),
        labour_multiplier=new_labour_mult.quantize(Decimal("0.01")),
        samples_count=previous_tuning["samples_count"] + 1,
    )


def generate_quote_from_template(
    template_code: str,
    specs: Dict[str, Any],
    materials_catalog: Dict[str, MaterialData],
    tuning: Optional[TuningData],
    labour_rate_per_hour: Decimal,
    overhead_pct: Decimal = Decimal("10"),
    margin_pct: Decimal = Decimal("25"),
) -> QuoteCostResult:
    """
    Generate a complete quote with BOM and pricing from a template.
    
    This is a convenience function that combines estimate_bom and compute_cost.
    
    Args:
        template_code: Template identifier
        specs: User specifications
        materials_catalog: Available materials with prices
        tuning: Optional tuning multipliers
        labour_rate_per_hour: Labour cost per hour
        overhead_pct: Overhead percentage
        margin_pct: Profit margin percentage
    
    Returns:
        QuoteCostResult with complete quote data
    """
    # Get the template to find labour hours
    templates = {t["code"]: t for t in DEFAULT_TEMPLATES}
    template = templates.get(template_code, {})
    base_labour_hours = Decimal(str(template.get("default_labour_hours", 4)))
    
    # Apply labour tuning if available
    if tuning:
        labour_hours = base_labour_hours * tuning["labour_multiplier"]
    else:
        labour_hours = base_labour_hours
    
    # Generate BOM
    estimation = estimate_bom(
        template_code=template_code,
        specs=specs,
        tuning=tuning,
        materials_catalog=materials_catalog,
    )
    
    # Calculate costs
    cost_breakdown = compute_cost(
        bom_items=estimation.bom,
        labour_hours=labour_hours,
        labour_rate_per_hour=labour_rate_per_hour,
        overhead_pct=overhead_pct,
        margin_pct=margin_pct,
    )
    
    return QuoteCostResult(
        bom=estimation.bom,
        cost_breakdown=cost_breakdown,
        recommended_price=cost_breakdown["total"],
        min_price=cost_breakdown["min_price"],
    )


# ==============================================================================
# HELPER FUNCTIONS FOR MODEL CONVERSION
# ==============================================================================


def material_to_data(material) -> MaterialData:
    """Convert a WeldingMaterial model instance to MaterialData dict."""
    return MaterialData(
        id=material.id,
        code=material.code,
        name=material.name,
        category=material.category,
        unit=material.unit,
        price_mwk=material.price_mwk,
        quantity_in_stock=material.quantity_in_stock,
    )


def tuning_to_data(tuning) -> TuningData:
    """Convert a WeldingEstimatorTuning model instance to TuningData dict."""
    return TuningData(
        tube_multiplier=tuning.tube_multiplier,
        paint_multiplier=tuning.paint_multiplier,
        consumable_multiplier=tuning.consumable_multiplier,
        labour_multiplier=tuning.labour_multiplier,
        samples_count=tuning.samples_count,
    )


def bom_items_to_json(bom_items: List[BOMItem]) -> List[Dict]:
    """Convert BOM items to JSON-serializable format."""
    return [
        {
            "material_code": item["material_code"],
            "material_name": item["material_name"],
            "category": item["category"],
            "quantity": str(item["quantity"]),
            "unit": item["unit"],
            "unit_price_mwk": str(item["unit_price_mwk"]),
            "line_total_mwk": str(item["line_total_mwk"]),
        }
        for item in bom_items
    ]


def cost_breakdown_to_json(breakdown: CostBreakdown) -> Dict:
    """Convert cost breakdown to JSON-serializable format."""
    return {
        "materials_cost": str(breakdown["materials_cost"]),
        "labour_cost": str(breakdown["labour_cost"]),
        "overhead_cost": str(breakdown["overhead_cost"]),
        "subtotal_before_margin": str(breakdown["subtotal_before_margin"]),
        "margin_amount": str(breakdown["margin_amount"]),
        "total": str(breakdown["total"]),
        "min_price": str(breakdown["min_price"]),
    }

