// Pure helpers for the Upload Analysis tab (no React, no network) so they can be unit-tested with node --test.

export const MODES = {
    single: {
        label: 'Single image',
        files: [{ slot: 1, label: 'Image', hint: 'GeoTIFF with any band count, or a JPG/PNG photo' }],
        needsDates: false,
    },
    optical_sar: {
        label: 'Optical + SAR',
        files: [
            { slot: 1, label: 'Optical image', hint: '3+ bands (e.g. Sentinel-2, Cartosat-2S)' },
            { slot: 2, label: 'SAR image', hint: '1-2 bands (VV/VH or HH/HV)' },
        ],
        needsDates: false,
    },
    bi_temporal: {
        label: 'Two dates (change)',
        files: [
            { slot: 1, label: 'Image, date 1', hint: 'same area, same CRS' },
            { slot: 2, label: 'Image, date 2', hint: 'same area, same CRS' },
        ],
        needsDates: true,
    },
};

export const SENSORS = ['auto', 'sentinel2', 'cartosat2s', 'bgrn', 'rgb', 'sar'];

export const EXAMPLES = {
    single: [
        'Describe this image',
        'Is there a water area?',
        'Is it a rural or an urban area?',
        'How many buildings are there?',
        'How many bands does this image have?',
    ],
    optical_sar: [
        'Where is the water?',
        'How much of the area is built-up?',
        'Map water and built-up areas',
        'Show flooded areas',
        'What is the resolution of each image?',
    ],
    bi_temporal: [
        'What changed?',
        'Has built-up area increased, decreased or remained unchanged?',
        'Has vegetation changed?',
        'Has the water area changed?',
        'What are the acquisition dates?',
    ],
};

export const STATUS_STYLES = {
    OK: { label: 'Answered', tone: 'ok' },
    NOT_AVAILABLE: { label: 'Not available', tone: 'warn' },
    REJECTED: { label: 'Rejected', tone: 'warn' },
    ERROR: { label: 'Error', tone: 'error' },
};

const CONFIDENCE_BASIS = {
    modality_agreement: 'optical/SAR agreement',
    'threshold_robustness x season_consistency': 'threshold robustness x season consistency',
    threshold_robustness: 'threshold robustness',
};

/** Missing inputs that block the upload button, as user-facing sentences. */
const IMAGE_EXT = /\.(png|jpe?g)$/i;

/** False for names like "sar 1" (extension lost when renaming); the server then detects the type from content. */
export const hasExtension = (name) => /\.[^.\\/\s]+$/.test(name || '');

/** Files that go up in photo (benchmark) mode: JPG/PNG, or files whose type the server must detect. */
export const needsPhotoMode = (name) => IMAGE_EXT.test(name || '') || !hasExtension(name);
const GEOTIFF_EXT = /\.tiff?$/i;

export function uploadProblems(mode, files, dates, benchmark = false) {
    const spec = MODES[mode];
    if (!spec) return ['Choose a mode.'];
    const problems = [];
    for (const f of spec.files) {
        const file = files[f.slot];
        if (!file) problems.push(`Add the ${f.label.toLowerCase()}.`);
        else if (!file.name) continue;
        else if (IMAGE_EXT.test(file.name) && !benchmark) {
            problems.push(`${file.name} is a PNG/JPEG. Upload a GeoTIFF (.tif), or turn on Benchmark mode under Advanced.`);
        } else if (hasExtension(file.name) && !GEOTIFF_EXT.test(file.name) && !IMAGE_EXT.test(file.name)) {
            problems.push(`${file.name} is not a supported image. Use a GeoTIFF (.tif/.tiff).`);
        }
    }
    if (spec.needsDates) {
        if (!dates[1] || !dates[2]) problems.push('Enter both acquisition dates.');
        else if (dates[1] === dates[2]) problems.push('The two dates must be different.');
    }
    return problems;
}

/** "92%" for a 0-1 value, "n/a" for null/undefined. */
export function formatConfidence(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return 'n/a';
    return `${Math.round(value * 100)}%`;
}

/** What the confidence number means for this answer. */
export function confidenceBasis(result) {
    if (!result || result.confidence === null || result.confidence === undefined) {
        return 'no confidence for this status';
    }
    const basis = result.details?.confidence_basis;
    if (basis) return CONFIDENCE_BASIS[basis] || basis;
    if (result.trace?.tool === 'image_metadata') return 'read directly from file metadata';
    return 'softmax probability of the answer';
}

export function humanize(name) {
    return String(name || '').replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}

export function formatMs(ms) {
    if (ms === null || ms === undefined) return '';
    return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${ms.toFixed(ms < 10 ? 2 : 0)} ms`;
}

/** Preview images (bases) and overlays from an upload + query result. */
export function splitEvidence(uploadId, files, result) {
    const bases = new Map();
    for (const f of files || []) {
        bases.set(`preview_${f.slot}`, {
            id: `preview_${f.slot}`,
            label: `File ${f.slot} (${f.filename})`,
            url: `/api/uploads/${uploadId}/preview/${f.slot}`,
        });
    }
    const overlays = [];
    for (const e of result?.evidence_images || []) {
        if (e.kind === 'overlay') overlays.push(e);
        else if (!bases.has(e.id)) bases.set(e.id, e);
    }
    return { bases: [...bases.values()], overlays };
}

// --- Earth Engine fetch helpers -------------------------------------------------------------

const KM_PER_DEG = 111.32;

/** [west, south, east, north] box of ``sizeKm`` x ``sizeKm`` centred on lat/lon. */
export function bboxAround(lat, lon, sizeKm) {
    const dLat = sizeKm / 2 / KM_PER_DEG;
    const dLon = sizeKm / 2 / (KM_PER_DEG * Math.cos((lat * Math.PI) / 180));
    const r = (v) => Math.round(v * 1e6) / 1e6;
    return [r(lon - dLon), r(lat - dLat), r(lon + dLon), r(lat + dLat)];
}

/** Width and height of a [west, south, east, north] box in km. */
export function bboxSizeKm([west, south, east, north]) {
    const midLat = (((south + north) / 2) * Math.PI) / 180;
    return { width: (east - west) * KM_PER_DEG * Math.cos(midLat), height: (north - south) * KM_PER_DEG };
}

/** Problems with an area / date ranges before calling POST /api/gee/fetch. */
export function geeFetchProblems(mode, bbox, ranges, maxKm = 10) {
    const problems = [];
    if (!bbox) problems.push('Choose an area (district or rectangle).');
    else {
        const { width, height } = bboxSizeKm(bbox);
        if (width > maxKm + 0.05 || height > maxKm + 0.05) {
            problems.push(`The area is ${width.toFixed(1)} x ${height.toFixed(1)} km; the maximum is ${maxKm} x ${maxKm} km.`);
        }
    }
    const needed = mode === 'bi_temporal' ? 2 : 1;
    for (let i = 0; i < needed; i += 1) {
        const [start, end] = ranges[i] || [];
        if (!start || !end) problems.push(`Enter date range ${needed > 1 ? i + 1 : ''}`.trim() + '.');
        else if (start >= end) problems.push(`Date range ${needed > 1 ? `${i + 1} ` : ''}must start before it ends.`);
    }
    return problems;
}

/** Where to get analysable GeoTIFFs (shown wherever a photo can't be analysed). */
export const GEOTIFF_SOURCES = [
    { label: "Use 'Fetch from Earth Engine' below (easiest)", href: null },
    { label: 'Copernicus Browser: Sentinel-2 L2A / Sentinel-1 GRD as GeoTIFF', href: 'https://browser.dataspace.copernicus.eu/' },
    { label: 'ASF Vertex: Sentinel-1 RTC GeoTIFF (calibrated SAR)', href: 'https://search.asf.alaska.edu/' },
    { label: 'ISRO Bhoonidhi: Cartosat / RISAT', href: 'https://bhoonidhi.nrsc.gov.in/' },
    { label: 'Or try the demo files in samples/', href: null },
];

/** Answers that say an input (photo / uncalibrated radar) can't be analysed. */
export function needsGeoTiffHint(text) {
    return /photo|GeoTIFF|calibrated|multispectral|near-infrared|PNG|JPEG/i.test(text || '');
}
