// Build downloadable reports (JSON + self-contained HTML) from an upload manifest and a query result.
import { confidenceBasis, formatConfidence, formatMs, humanize, STATUS_STYLES } from './format.js';

export function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

export function buildReportJson(upload, result, generatedAt = new Date().toISOString()) {
    return {
        report: 'SatQuery AI - upload analysis',
        generated_at: generatedAt,
        // Everyday-language answer first; `upload` and `query` below are the technical details.
        answer: {
            question: result.question,
            status: result.status,
            ...(result.plain || { headline: null, note: 'No plain-language answer in this result.' }),
        },
        upload: {
            upload_id: upload.upload_id,
            mode: upload.mode,
            files: (upload.files || []).map((f) => ({
                slot: f.slot,
                filename: f.filename,
                kind: f.kind,
                date: f.date,
                bands: f.metadata?.band_count,
                crs: f.metadata?.crs,
                resolution: f.metadata?.resolution,
                band_roles: f.bands?.roles,
            })),
            warnings: upload.warnings || [],
            source: upload.source || null,
        },
        query: result,
    };
}

/**
 * Self-contained HTML report. ``images`` maps evidence id -> data: URL (already fetched),
 * so the file works offline. All text goes through escapeHtml.
 */
export function buildReportHtml(upload, result, images = {}, generatedAt = new Date().toISOString()) {
    const status = STATUS_STYLES[result.status]?.label || result.status;
    const trace = result.trace || {};
    const fileRows = (upload.files || [])
        .map((f) => `<tr><td>${escapeHtml(f.slot)}</td><td>${escapeHtml(f.filename)}</td><td>${escapeHtml(f.kind)}</td>`
            + `<td>${escapeHtml(f.date || '-')}</td><td>${escapeHtml(f.metadata?.band_count)}</td>`
            + `<td>${escapeHtml(f.metadata?.crs || 'none')}</td></tr>`)
        .join('');
    const stepRows = (trace.steps || [])
        .map((s) => `<tr><td>${escapeHtml(humanize(s.step))}</td><td>${escapeHtml(s.status)}</td>`
            + `<td>${escapeHtml(formatMs(s.duration_ms))}</td><td><code>${escapeHtml(JSON.stringify(s.detail))}</code></td></tr>`)
        .join('');
    const figures = (result.evidence_images || [])
        .filter((e) => images[e.id])
        .map((e) => `<figure><img src="${escapeHtml(images[e.id])}" alt="${escapeHtml(e.label)}">`
            + `<figcaption>${escapeHtml(e.label)}${(e.legend || []).map((l) =>
                ` <span class="sw" style="background:${escapeHtml(l.color)}"></span>${escapeHtml(l.label)}`).join('')}`
            + '</figcaption></figure>')
        .join('');

    const plain = result.plain;
    const list = (items) => `<ul>${items.map((i) => `<li>${escapeHtml(i)}</li>`).join('')}</ul>`;
    const plainHtml = plain ? `<div class="plain">
<p class="headline">${escapeHtml(plain.headline)}</p>
<p>${escapeHtml(plain.what_it_means)}</p>
${plain.key_numbers?.length ? `<h3>Key numbers</h3>${list(plain.key_numbers)}` : ''}
<p><span class="badge ${escapeHtml(String(plain.confidence?.level || '').replace(/\s+/g, '-').toLowerCase())}">${escapeHtml(plain.confidence?.level)} confidence</span> ${escapeHtml(plain.confidence?.reason)}</p>
<p><strong>How we know:</strong> ${escapeHtml(plain.how_we_know)}</p>
${plain.caveats?.length ? `<div class="caveats"><strong>Please note</strong>${list(plain.caveats)}</div>` : ''}
${plain.next_step ? `<p><strong>Next, you could ask:</strong> ${escapeHtml(plain.next_step)}</p>` : ''}
</div>` : '<p>No plain-language answer in this result.</p>';

    return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>SatQuery AI report</title>
<style>
body{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#111}
h1{font-size:1.4rem}h2{font-size:1.1rem;margin-top:1.6rem}
table{border-collapse:collapse;width:100%;font-size:.85rem}td,th{border:1px solid #ccc;padding:.3rem .5rem;text-align:left;vertical-align:top}
code{white-space:pre-wrap;word-break:break-word;font-size:.75rem}.answer{white-space:pre-wrap;background:#f4f6f8;padding:.8rem;border-radius:6px}
figure{display:inline-block;margin:.5rem;max-width:45%}figure img{max-width:100%;image-rendering:pixelated;border:1px solid #ccc}
.plain{background:#f4f8f6;border:1px solid #cfe3da;border-radius:8px;padding:.4rem 1rem}.headline{font-size:1.25rem;font-weight:600}
.badge{display:inline-block;border-radius:999px;padding:.05rem .6rem;font-size:.8rem;font-weight:600;border:1px solid}
.badge.high{background:#e7f6ec;color:#116329;border-color:#8fd19e}.badge.medium{background:#fff6e0;color:#7a4d00;border-color:#f0c36d}
.badge.low{background:#fdecec;color:#8a1c1c;border-color:#f19a9a}.badge.not-rated{background:#eee;color:#444;border-color:#bbb}
.caveats{background:#fff8e6;border:1px solid #f0d58c;border-radius:6px;padding:.5rem .8rem;margin:.6rem 0}
.technical{margin-top:2.2rem;border-top:2px solid #ddd}
.sw{display:inline-block;width:.8rem;height:.8rem;margin:0 .2rem 0 .6rem;vertical-align:middle;border:1px solid #999}
</style></head><body>
<h1>SatQuery AI - upload analysis report</h1>
<p>Generated ${escapeHtml(generatedAt)} &middot; upload <code>${escapeHtml(upload.upload_id)}</code> &middot; mode ${escapeHtml(upload.mode)}</p>
<h2>Question</h2><p>${escapeHtml(result.question)}</p>
<h2>Answer</h2>
${plainHtml}
<div class="technical">
<h2>Technical details</h2>
<h3>Technical answer</h3><p><strong>${escapeHtml(status)}</strong> &middot; confidence ${escapeHtml(formatConfidence(result.confidence))} (${escapeHtml(confidenceBasis(result))})</p>
<div class="answer">${escapeHtml(result.answer)}</div>
<h2>Evidence</h2>${figures || '<p>No evidence images.</p>'}
<h2>Execution trace</h2>
<p>Task <strong>${escapeHtml(trace.task)}</strong>${trace.rerouted_from ? ` (rerouted from ${escapeHtml(trace.rerouted_from)})` : ''}
 &middot; tool <strong>${escapeHtml(trace.tool || '-')}</strong> ${escapeHtml(trace.tool_version || '')}
 &middot; ${escapeHtml(formatMs(trace.duration_ms))} &middot; status ${escapeHtml(trace.status)}</p>
<p>Params: <code>${escapeHtml(JSON.stringify(trace.params || {}))}</code></p>
${upload.source ? `<p>Source: ${escapeHtml(upload.source.provider)} &middot; ${escapeHtml(upload.source.products.map((p) => `${p.collection.join(' + ')} ${p.date_range.join(' to ')} (${p.scenes} scenes, bands ${p.bands.join(',')})`).join('; '))} &middot; ${escapeHtml(upload.source.crs)}, ${escapeHtml(upload.source.scale_m)} m</p>` : ''}
<table><tr><th>Step</th><th>Status</th><th>Duration</th><th>Detail</th></tr>${stepRows}</table>
<h2>Inputs</h2>
<table><tr><th>Slot</th><th>File</th><th>Kind</th><th>Date</th><th>Bands</th><th>CRS</th></tr>${fileRows}</table>
</div>
</body></html>`;
}

export function reportFilename(upload, result, ext) {
    const id = String(result?.query_id || upload?.upload_id || 'report').slice(0, 8);
    return `satquery-report-${id}.${ext}`;
}
