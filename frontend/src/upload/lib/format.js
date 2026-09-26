// Pure helpers for the Upload Analysis tab (no React, no network) so they can be unit-tested with node --test.

export const MODES = {
    single: {
        label: 'Single image',
        files: [{ slot: 1, label: 'Image', hint: 'GeoTIFF (any band count)' }],
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
        'How many bands does this image have?',
    ],
    optical_sar: [
        'Where is the water?',
        'How much of the area is built-up?',
        'Map water and built-up areas',
        'What is the resolution of each image?',
    ],
    bi_temporal: [
        'What changed?',
        'Has built-up area increased, decreased or remained unchanged?',
        'Has vegetation changed?',
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
export function uploadProblems(mode, files, dates) {
    const spec = MODES[mode];
    if (!spec) return ['Choose a mode.'];
    const problems = [];
    for (const f of spec.files) {
        if (!files[f.slot]) problems.push(`Add the ${f.label.toLowerCase()}.`);
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
