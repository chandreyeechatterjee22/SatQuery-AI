// Run with: npm test   (node's built-in test runner, no extra dependencies)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
    confidenceBasis, EXAMPLES, formatConfidence, formatMs, humanize, MODES, splitEvidence, uploadProblems,
} from './format.js';
import { buildReportHtml, buildReportJson, escapeHtml, reportFilename } from './report.js';

const upload = {
    upload_id: 'abc123def456',
    mode: 'optical_sar',
    files: [
        { slot: 1, filename: 'opt.tif', kind: 'optical', metadata: { band_count: 4, crs: 'EPSG:32643' }, bands: { roles: { red: 3 } } },
        { slot: 2, filename: 's1.tif', kind: 'sar', metadata: { band_count: 2, crs: 'EPSG:32643' } },
    ],
    warnings: ['File 2: SAR bands assumed to be VV, VH'],
};
const result = {
    query_id: 'q9876543210',
    question: 'Where is the <water>?',
    status: 'OK',
    answer: 'Water: 25.00% of the area.\nBoth modalities must agree.',
    confidence: 0.9412,
    evidence_images: [
        { id: 'preview_1', kind: 'preview', label: 'File 1 preview', url: '/api/uploads/abc/preview/1' },
        { id: 'water_overlay', kind: 'overlay', base: 'preview_1', label: 'Water mask', url: '/api/q/water.png',
          legend: [{ label: 'optical + SAR agree', color: '#1f6feb' }] },
    ],
    details: { confidence_basis: 'modality_agreement' },
    trace: {
        task: 'water_builtup', tool: 'optical_sar_mapper', tool_version: '1.0.0', params: { classes: ['water'] },
        duration_ms: 291.4, status: 'OK',
        steps: [{ step: 'classify_task', status: 'ok', duration_ms: 0.1, detail: { task: 'water_builtup' } }],
    },
};

test('every mode has files and example questions', () => {
    for (const mode of Object.keys(MODES)) {
        assert.ok(MODES[mode].files.length >= 1);
        assert.ok(EXAMPLES[mode].length >= 3);
    }
});

test('uploadProblems checks files and bi_temporal dates', () => {
    assert.deepEqual(uploadProblems('single', {}, {}), ['Add the image.']);
    assert.deepEqual(uploadProblems('single', { 1: {} }, {}), []);
    assert.equal(uploadProblems('optical_sar', { 1: {} }, {}).length, 1);
    assert.deepEqual(uploadProblems('bi_temporal', { 1: {}, 2: {} }, { 1: '2024-01-01' }),
        ['Enter both acquisition dates.']);
    assert.deepEqual(uploadProblems('bi_temporal', { 1: {}, 2: {} }, { 1: '2024-01-01', 2: '2024-01-01' }),
        ['The two dates must be different.']);
    assert.deepEqual(uploadProblems('bi_temporal', { 1: {}, 2: {} }, { 1: '2024-01-01', 2: '2025-01-01' }), []);
});

test('confidence formatting and basis', () => {
    assert.equal(formatConfidence(0.9412), '94%');
    assert.equal(formatConfidence(null), 'n/a');
    assert.equal(formatConfidence(undefined), 'n/a');
    assert.equal(confidenceBasis(result), 'optical/SAR agreement');
    assert.equal(confidenceBasis({ confidence: 0.8, trace: { tool: 'rs_vqa' }, details: {} }),
        'softmax probability of the answer');
    assert.equal(confidenceBasis({ confidence: 1, trace: { tool: 'image_metadata' } }), 'read directly from file metadata');
    assert.equal(confidenceBasis({ confidence: null }), 'no confidence for this status');
});

test('small formatters', () => {
    assert.equal(humanize('validate_params'), 'Validate params');
    assert.equal(formatMs(0.05), '0.05 ms');
    assert.equal(formatMs(291.4), '291 ms');
    assert.equal(formatMs(2500), '2.50 s');
});

test('splitEvidence separates bases and overlays and adds upload previews', () => {
    const { bases, overlays } = splitEvidence('abc', upload.files, result);
    assert.deepEqual(bases.map((b) => b.id), ['preview_1', 'preview_2']);
    assert.equal(bases[1].url, '/api/uploads/abc/preview/2');
    assert.deepEqual(overlays.map((o) => o.id), ['water_overlay']);
    assert.deepEqual(splitEvidence('abc', upload.files, null).overlays, []);
});

test('escapeHtml escapes markup', () => {
    assert.equal(escapeHtml('<b a="1">&\'</b>'), '&lt;b a=&quot;1&quot;&gt;&amp;&#39;&lt;/b&gt;');
    assert.equal(escapeHtml(null), '');
});

test('JSON report keeps the full query result and a file summary', () => {
    const r = buildReportJson(upload, result, '2026-09-26T00:00:00Z');
    assert.equal(r.generated_at, '2026-09-26T00:00:00Z');
    assert.deepEqual(r.query, result);
    assert.equal(r.upload.files[0].bands, 4);
    assert.deepEqual(r.upload.files[0].band_roles, { red: 3 });
});

test('HTML report is escaped, self-contained and includes trace + evidence', () => {
    const html = buildReportHtml(upload, result, { water_overlay: 'data:image/png;base64,AAAA' }, 'now');
    assert.ok(html.startsWith('<!doctype html>'));
    assert.ok(html.includes('Where is the &lt;water&gt;?'));
    assert.ok(!html.includes('<water>'));
    assert.ok(html.includes('confidence 94% (optical/SAR agreement)'));
    assert.ok(html.includes('src="data:image/png;base64,AAAA"'));
    assert.ok(!html.includes('/api/q/water.png'), 'evidence must be embedded, not linked');
    assert.ok(html.includes('optical_sar_mapper'));
    assert.ok(html.includes('Classify task'));
    assert.ok(html.includes('opt.tif'));
});

test('report filenames', () => {
    assert.equal(reportFilename(upload, result, 'json'), 'satquery-report-q9876543.json');
    assert.equal(reportFilename(upload, null, 'html'), 'satquery-report-abc123de.html');
});
