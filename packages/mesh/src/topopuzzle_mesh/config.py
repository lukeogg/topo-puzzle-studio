"""Settings schema shared by the CLI, the API, and the geometry core.

Everything downstream is driven by :class:`GenerateSettings`.  The model is a
pydantic v2 model so it validates identically whether the values arrive from the
CLI, an HTTP request body, or a test fixture.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class AssemblyMode(str, Enum):
    """How the pieces relate on the plate."""

    SEPARATE = "separate-pieces"
    PRINT_IN_PLACE = "print-in-place"


class ConnectorStyle(str, Enum):
    """Connector profile.  Print-in-place forbids undercuts, so it is limited to
    straight-walled tabs; separate-pieces may use knob styles with an undercut."""

    ROUNDED_TAB = "rounded-tab"  # jigsaw-style knob, separate-pieces only
    STRAIGHT_TAB = "straight-tab"  # rectangular, undercut-free — safe print-in-place
    ORGANIC_TAB = "organic-tab"  # seeded blobby knob, separate-pieces only
    VORONOI_TAB = "voronoi-tab"  # seeded faceted cell knob, separate-pieces only
    NONE = "none"


#: Styles with an undercut — unsafe for print-in-place (would fuse layer-to-layer).
UNDERCUT_STYLES = frozenset(
    {ConnectorStyle.ROUNDED_TAB, ConnectorStyle.ORGANIC_TAB, ConnectorStyle.VORONOI_TAB}
)


class RenderMode(str, Enum):
    DEBOSS = "deboss"
    EMBOSS = "emboss"
    INLAY = "inlay"


class OverlayClass(str, Enum):
    """OSM feature classes that can be draped onto the terrain."""

    ROADS = "roads"
    TRAILS = "trails"
    WATERWAYS = "waterways"
    LAKES = "lakes"


class Bounds(BaseModel):
    """Geographic bounding box in EPSG:4326 (lon/lat degrees)."""

    west: float = Field(..., ge=-180, le=180)
    south: float = Field(..., ge=-90, le=90)
    east: float = Field(..., ge=-180, le=180)
    north: float = Field(..., ge=-90, le=90)

    @model_validator(mode="after")
    def _ordered(self) -> "Bounds":
        if self.east <= self.west:
            raise ValueError("east must be greater than west")
        if self.north <= self.south:
            raise ValueError("north must be greater than south")
        return self

    @property
    def center(self) -> tuple[float, float]:
        return ((self.west + self.east) / 2.0, (self.south + self.north) / 2.0)

    @classmethod
    def from_csv(cls, s: str) -> "Bounds":
        """Parse a ``west,south,east,north`` string (CLI ``--bbox``)."""
        parts = [float(p) for p in s.split(",")]
        if len(parts) != 4:
            raise ValueError("bbox must be 'west,south,east,north'")
        return cls(west=parts[0], south=parts[1], east=parts[2], north=parts[3])


class ConnectorSettings(BaseModel):
    style: ConnectorStyle = ConnectorStyle.ROUNDED_TAB
    #: Tab width as a fraction of the shared edge length.
    width_frac: float = Field(0.28, gt=0.05, le=0.6)
    #: How far the tab protrudes past the seam, in mm.
    depth_mm: float = Field(6.0, gt=0.5, le=40.0)
    #: Neck / minimum wall thickness guardrail in mm (3 * 0.4 nozzle default).
    min_wall_mm: float = Field(1.2, gt=0.0)
    #: Per-side clearance for separate-pieces fit, mm.
    clearance_mm: float = Field(0.20, ge=0.0, le=0.6)
    #: Deterministic seed for tab orientation alternation.
    seed: int = 1


class WaterSettings(BaseModel):
    enabled: bool = False
    #: Elevations at or below this (metres, real-world) are flattened to it.
    threshold_m: float = 0.0
    #: Recess the flattened water surface by this much (mm) for a visible edge.
    recess_mm: float = 0.4


class ElevationBand(BaseModel):
    #: Lower bound of the band in real-world metres (inclusive).
    min_m: float
    #: Human label / colour name, used in color-changes.txt.
    name: str
    #: Optional hex colour for previews and the manifest.
    hex: str | None = None


class MagnetSettings(BaseModel):
    """Cylindrical magnet pockets recessed into a piece's flat bottom.

    The pocket opens at the bottom face (magnet inserted from below) and stops
    inside the base slab, so it never breaches the terrain surface.  Intended to
    seat the finished model/pieces on a ferrous base or tray.
    """

    enabled: bool = False
    diameter_mm: float = Field(6.0, gt=1.0, le=30.0)
    depth_mm: float = Field(2.0, gt=0.4, le=20.0)
    #: Minimum wall left between the pocket and the piece edge, per side.
    margin_mm: float = Field(2.0, ge=0.5)


class TraySettings(BaseModel):
    enabled: bool = False
    wall_mm: float = Field(4.0, gt=1.0)
    border_h_mm: float = Field(6.0, gt=1.0)
    #: Gap between the tray recess and the assembled puzzle footprint, per side.
    fit_gap_mm: float = Field(0.4, ge=0.0)
    #: When the tray exceeds the plate, split it into halves joined by alignment
    #: pins (each half prints separately) instead of leaving it un-printable.
    split_oversize: bool = True
    pin_diameter_mm: float = Field(3.0, gt=0.5, le=10.0)
    pin_length_mm: float = Field(8.0, gt=2.0, le=40.0)
    #: Per-side clearance on the pin holes so the halves press together, mm.
    pin_clearance_mm: float = Field(0.15, ge=0.0, le=0.5)


class OverlaySettings(BaseModel):
    """Tier-3: OSM feature overlays draped onto the terrain surface."""

    enabled: bool = False
    classes: list[OverlayClass] = Field(
        default_factory=lambda: [OverlayClass.ROADS, OverlayClass.WATERWAYS, OverlayClass.LAKES]
    )
    #: How features are rendered: recessed groove, raised ribbon, or flush inlay.
    render: RenderMode = RenderMode.DEBOSS
    #: Groove depth / raised height / inlay shell thickness, in mm.
    relief_mm: float = Field(0.6, gt=0.1, le=3.0)
    #: Drop any line class whose ribbon would render below this width (mm).
    min_width_mm: float = Field(1.0, ge=0.4)
    #: Multiply the per-class real-world widths (roads/trails/waterways).
    width_scale: float = Field(1.0, gt=0.0, le=20.0)
    #: Offline alternative to Overpass: a GeoJSON file of features to overlay.
    geojson_path: str | None = None


class LandCoverClass(BaseModel):
    """One land-cover class → filament mapping."""

    code: int
    name: str = ""
    hex: str | None = None


class LandCoverSettings(BaseModel):
    """Tier-4: colour the terrain's top shell by land cover (discrete classes)."""

    enabled: bool = False
    #: Thickness of the per-class coloured top shell, in mm.
    shell_mm: float = Field(0.8, gt=0.1, le=5.0)
    #: Drop regions smaller than this at physical scale (purge-waste guardrail).
    min_region_mm2: float = Field(3.0, ge=0.0)
    #: Offline path to a classified raster; else ESA WorldCover (network).
    raster_path: str | None = None
    #: Explicit class→filament mapping; empty → auto from the grid's most common
    #: classes, capped at ``max_classes`` (one AMS's worth by default).
    mapping: list[LandCoverClass] = Field(default_factory=list)
    max_classes: int = Field(4, ge=1, le=8)


class BuildVolume(BaseModel):
    """Usable print area.  Default is a conservative Bambu P2S window."""

    x_mm: float = 250.0
    y_mm: float = 250.0
    z_mm: float = 250.0


class GenerateSettings(BaseModel):
    """The full, validated configuration for one generation run."""

    # --- source ---
    bounds: Bounds | None = None
    provider: str = "geotiff"
    geotiff_path: str | None = None
    place_name: str | None = None

    # --- physical size ---
    size_mm: float = Field(180.0, gt=10.0, le=1000.0)  # longest edge
    base_mm: float = Field(3.0, ge=0.5, le=50.0)
    z_exaggeration: float = Field(1.8, gt=0.0, le=10.0)

    # --- layout ---
    rows: int = Field(1, ge=1, le=12)
    cols: int = Field(1, ge=1, le=12)
    assembly: AssemblyMode = AssemblyMode.SEPARATE
    #: Print-in-place seam gap (>= nozzle width). Ignored for separate-pieces.
    gap_mm: float = Field(0.4, ge=0.1, le=2.0)
    connector: ConnectorSettings = Field(default_factory=ConnectorSettings)

    # --- raster processing ---
    max_grid: int = Field(400, ge=32, le=2000)
    smoothing_sigma: float = Field(0.0, ge=0.0, le=10.0)
    water: WaterSettings = Field(default_factory=WaterSettings)
    #: Warn when interpolated nodata exceeds this fraction of the grid.
    nodata_warn_frac: float = 0.05

    # --- features ---
    labels: bool = False
    label_depth_mm: float = 0.6
    tray: TraySettings = Field(default_factory=TraySettings)
    magnets: MagnetSettings = Field(default_factory=MagnetSettings)
    overlays: OverlaySettings = Field(default_factory=OverlaySettings)
    landcover: LandCoverSettings = Field(default_factory=LandCoverSettings)
    bands: list[ElevationBand] = Field(default_factory=list)
    #: Tier-2 colour: also emit per-band contour slabs as named 3MF objects
    #: (requires ``bands``; the assembled solid is sliced at each band boundary).
    contour_bands: bool = False

    # --- printer constraints ---
    build_volume: BuildVolume = Field(default_factory=BuildVolume)
    min_feature_mm: float = 1.2  # 3 * 0.4 mm perimeters

    # --- export ---
    formats: list[str] = Field(default_factory=lambda: ["stl", "3mf"])

    @model_validator(mode="after")
    def _defaults_by_assembly(self) -> "GenerateSettings":
        # Print-in-place must not use undercut connectors.
        if self.assembly is AssemblyMode.PRINT_IN_PLACE:
            if self.connector.style in UNDERCUT_STYLES:
                self.connector.style = ConnectorStyle.STRAIGHT_TAB
        return self

    @property
    def piece_count(self) -> int:
        return self.rows * self.cols

    @property
    def is_solid(self) -> bool:
        return self.rows == 1 and self.cols == 1
