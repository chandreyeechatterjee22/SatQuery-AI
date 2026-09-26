import React, { useEffect, useMemo, useRef, useState } from 'react';
import L from 'leaflet';
import { MapContainer, TileLayer, FeatureGroup, Rectangle, useMap } from 'react-leaflet';
import { EditControl } from 'react-leaflet-draw';
import { FiCloud, FiChevronDown, FiChevronRight } from 'react-icons/fi';
import 'leaflet/dist/leaflet.css';
import 'leaflet-draw/dist/leaflet.draw.css';
import { describeError, fetchAreas, fetchGeeStatus, fetchLocation, fetchStates, geeFetch } from '../api';
import { bboxAround, bboxSizeKm, geeFetchProblems } from './lib/format.js';
import DistrictSelect from '../components/DistrictSelect';
import MapAutoResize from '../components/MapAutoResize';
import ImageryDepthGuard from '../components/ImageryDepthGuard';
import { ESRI_IMAGERY_URL, imageryTileOptions } from './lib/mapTiles.js';

const inputClass = 'w-full rounded-lg border border-space-700 bg-space-900/70 px-2 py-1.5 text-xs text-white '
    + 'focus:border-accent-cyan focus:outline-none';
const MODES = [['single', 'Single image'], ['optical_sar', 'Optical + SAR'], ['bi_temporal', 'Two dates']];
const DEFAULT_RANGES = [['2024-01-01', '2024-03-31'], ['2025-01-01', '2025-03-31']];

/** Leaflet must re-measure its container when the map is enlarged or shrunk. */
const ResizeWatcher = ({ expanded }) => {
    const map = useMap();
    useEffect(() => { const t = setTimeout(() => map.invalidateSize(), 60); return () => clearTimeout(t); }, [expanded, map]);
    return null;
};

/** Fly the preview map to the chosen district. */
const FlyTo = ({ centre }) => {
    const map = useMap();
    useEffect(() => { if (centre) map.flyTo([centre.lat, centre.lon], centre.zoom, { duration: 1 }); }, [centre, map]);
    return null;
};

const DEFAULT_CENTRE = { lat: 12.93, lon: 77.66, zoom: 12 };  // Bellandur, Bengaluru

/** Esri imagery that never shows "Map data not yet available" tiles (see ImageryDepthGuard). */
const GuardedImagery = () => {
    const ref = useRef(null);
    const opts = imageryTileOptions(window.devicePixelRatio);
    return (
        <>
            <TileLayer url={ESRI_IMAGERY_URL} attribution="Esri" {...opts} ref={ref} />
            <ImageryDepthGuard layerRef={ref} baseMaxNativeZoom={opts.maxNativeZoom} />
        </>
    );
};

/** Re-create the editable rectangle if the map was re-mounted (e.g. after switching area type). */
const RestoreRectangle = ({ drawn, groupRef }) => {
    useEffect(() => {
        const group = groupRef.current;
        if (drawn && group && group.getLayers().length === 0) {
            L.rectangle([[drawn[1], drawn[0]], [drawn[3], drawn[2]]], { color: '#5BC0BE' }).addTo(group);
        }
    }, [drawn, groupRef]);
    return null;
};

/** "Fetch from Earth Engine": area + dates -> analysis-ready GeoTIFFs -> a normal upload. */
const GeeFetch = ({ onFetched, disabled }) => {
    const [open, setOpen] = useState(false);
    const [status, setStatus] = useState(null);       // {configured, reason, max_side_km}
    const [mode, setMode] = useState('optical_sar');
    const [areaKind, setAreaKind] = useState('district');
    const [states, setStates] = useState([]);
    const [areas, setAreas] = useState([]);
    const [majorCities, setMajorCities] = useState([]);
    const [state, setState] = useState('');
    const [area, setArea] = useState('');
    const [centre, setCentre] = useState(null);       // {lat, lon, zoom}
    const [sizeKm, setSizeKm] = useState(5);
    const [drawn, setDrawn] = useState(null);         // [w, s, e, n]
    const [ranges, setRanges] = useState(DEFAULT_RANGES);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [expanded, setExpanded] = useState(false);
    const groupRef = useRef(null);

    useEffect(() => {
        if (!open || status) return;
        fetchGeeStatus().then(setStatus)
            .catch((err) => setStatus({ configured: false, reason: describeError(err) }));
        fetchStates().then((d) => setStates(d.states || [])).catch(() => {});
    }, [open, status]);

    useEffect(() => {
        let stale = false;
        setAreas([]); setMajorCities([]); setArea(''); setCentre(null);
        if (state) {
            fetchAreas(state).then((d) => {
                if (stale) return;
                setAreas(d.areas || []);
                setMajorCities(d.major_cities || []);
            }).catch(() => {});
        }
        return () => { stale = true; };
    }, [state]);

    useEffect(() => {
        setCentre(null);
        if (state && area) fetchLocation(state, area).then((l) => setCentre({ lat: l.lat, lon: l.lon, zoom: l.zoom })).catch(() => {});
    }, [state, area]);

    const bbox = useMemo(() => {
        if (areaKind === 'draw') return drawn;
        return centre ? bboxAround(centre.lat, centre.lon, Number(sizeKm)) : null;
    }, [areaKind, drawn, centre, sizeKm]);
    const maxKm = status?.max_side_km || 10;
    const problems = geeFetchProblems(mode, bbox, ranges, maxKm);
    const size = bbox ? bboxSizeKm(bbox) : null;

    const setRange = (i, j, value) => setRanges(ranges.map((r, k) => (k === i ? r.map((v, m) => (m === j ? value : v)) : r)));

    const toBbox = (layer) => {
        const b = layer.getBounds();
        return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => Math.round(v * 1e6) / 1e6);
    };
    const onCreated = (e) => {
        // Keep only the newest rectangle; it stays in the group so it can be edited (resized / moved).
        groupRef.current?.getLayers().forEach((l) => { if (l !== e.layer) groupRef.current.removeLayer(l); });
        setDrawn(toBbox(e.layer));
    };
    const onEdited = (e) => e.layers.eachLayer((l) => setDrawn(toBbox(l)));
    const onDeleted = () => { if (!groupRef.current?.getLayers().length) setDrawn(null); };

    const submit = async () => {
        if (problems.length || busy) return;
        setBusy(true);
        setError('');
        try {
            const used = mode === 'bi_temporal' ? ranges : [ranges[0]];
            onFetched(await geeFetch(mode, bbox, used));
        } catch (err) {
            setError(describeError(err));
        } finally {
            setBusy(false);
        }
    };

    const notConfigured = status && !status.configured;
    return (
        <div className="rounded-lg border border-white/[0.07] bg-space-800 p-5">
            <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 text-left">
                {open ? <FiChevronDown /> : <FiChevronRight />}
                <FiCloud className="text-accent-cyan" />
                <span className="text-base font-semibold text-white">Fetch from Earth Engine</span>
            </button>
            {open && (
                <div className="mt-3 space-y-3 text-xs">
                    <p className="text-gray-400">Downloads analysis-ready Sentinel-2 (and Sentinel-1 for Optical + SAR) GeoTIFFs
                        for a small area (max {maxKm} x {maxKm} km) and uploads them for you.</p>

                    <div className="grid grid-cols-3 gap-1" role="radiogroup" aria-label="Fetch mode">
                        {MODES.map(([key, label]) => (
                            <button key={key} type="button" role="radio" aria-checked={mode === key} onClick={() => setMode(key)}
                                className={`rounded-lg border px-1 py-1.5 ${mode === key ? 'border-accent-cyan bg-accent-cyan/15 text-accent-cyan'
                                    : 'border-space-700 text-gray-300 hover:border-accent-cyan/60'}`}>{label}</button>
                        ))}
                    </div>

                    <div className="flex gap-3 text-gray-300">
                        <label className="flex items-center gap-1"><input type="radio" name="gee-area" checked={areaKind === 'district'}
                            onChange={() => setAreaKind('district')} /> State / UT and district</label>
                        <label className="flex items-center gap-1"><input type="radio" name="gee-area" checked={areaKind === 'draw'}
                            onChange={() => setAreaKind('draw')} /> Draw rectangle</label>
                    </div>

                    {areaKind === 'district' ? (
                        <div className="space-y-2">
                            <div className="grid grid-cols-2 gap-2">
                                <label className="text-gray-400">State / UT
                                    <select value={state} onChange={(e) => setState(e.target.value)} className={`${inputClass} mt-1`} aria-label="State / UT">
                                        <option value="">Select state / UT</option>
                                        {states.map((s) => <option key={s}>{s}</option>)}
                                    </select>
                                </label>
                                <label className="text-gray-400">District / City
                                    <DistrictSelect value={area} onChange={(e) => setArea(e.target.value)} areas={areas} majorCities={majorCities}
                                        disabled={!state} className={`${inputClass} mt-1`} aria-label="District / City" placeholder="Select" />
                                </label>
                            </div>
                            <label className="block text-gray-400">Box size around the district centre (km)
                                <input type="number" min="1" max={maxKm} step="0.5" value={sizeKm}
                                    onChange={(e) => setSizeKm(e.target.value)} className={`${inputClass} mt-1`} aria-label="Box size in km" />
                            </label>
                            <p className="text-gray-500">Large districts are only partly covered — use Draw rectangle for a specific spot.</p>
                            <div className="h-48 overflow-hidden rounded-lg border border-space-700" data-testid="gee-district-map">
                                <MapContainer center={[DEFAULT_CENTRE.lat, DEFAULT_CENTRE.lon]} zoom={5} className="h-full w-full" scrollWheelZoom={false}>
                                    <GuardedImagery />
                                    <MapAutoResize />
                                    <FlyTo centre={centre} />
                                    {bbox && <Rectangle bounds={[[bbox[1], bbox[0]], [bbox[3], bbox[2]]]} pathOptions={{ color: '#5BC0BE', weight: 2 }} />}
                                </MapContainer>
                            </div>
                        </div>
                    ) : (
                        <>
                            {expanded && <div className="fixed inset-0 z-[2999] bg-black/60" onClick={() => setExpanded(false)} />}
                            <div data-testid="gee-mini-map"
                                className={expanded
                                    ? 'fixed inset-4 sm:inset-10 z-[3000] flex flex-col gap-2 rounded-lg border border-white/10 bg-space-900 p-3'
                                    : 'flex flex-col gap-2'}>
                                {expanded && (
                                    <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-gray-200">
                                        <span>Draw a rectangle (square tool), or resize/move it with the edit tool (pencil) and click Save.</span>
                                        <span className="text-gray-400">{size ? `Area: ${size.width.toFixed(1)} x ${size.height.toFixed(1)} km (max ${maxKm} x ${maxKm})` : 'No area yet'}</span>
                                        <button type="button" onClick={() => setExpanded(false)}
                                            className="rounded-full bg-white px-4 py-1.5 font-medium text-primary hover:bg-soft-stone">Done</button>
                                    </div>
                                )}
                                <div className={`${expanded ? 'flex-1' : 'h-72'} overflow-hidden rounded-lg border border-space-700`}>
                                    {/* Opens on the chosen district when there is one, else on Bellandur. */}
                                    <MapContainer center={[(centre || DEFAULT_CENTRE).lat, (centre || DEFAULT_CENTRE).lon]}
                                        zoom={centre ? Math.max(centre.zoom, 11) : DEFAULT_CENTRE.zoom} className="h-full w-full">
                                        <GuardedImagery />
                                    <MapAutoResize />
                                        <ResizeWatcher expanded={expanded} />
                                        <FeatureGroup ref={groupRef}>
                                            <EditControl position="topleft" onCreated={onCreated} onEdited={onEdited} onDeleted={onDeleted}
                                                // showArea: false avoids leaflet-draw 1.0.4's readableArea bug ('type is not defined').
                                                draw={{ rectangle: { showArea: false, shapeOptions: { color: '#5BC0BE' } }, polygon: false,
                                                    polyline: false, circle: false, circlemarker: false, marker: false }} />
                                            <RestoreRectangle drawn={drawn} groupRef={groupRef} />
                                        </FeatureGroup>
                                    </MapContainer>
                                </div>
                                {!expanded && (
                                    <button type="button" onClick={() => setExpanded(true)}
                                        className="self-start rounded-lg border border-space-700 px-3 py-1 text-gray-200 hover:border-accent-cyan hover:text-accent-cyan">
                                        Enlarge map
                                    </button>
                                )}
                            </div>
                        </>
                    )}
                    {size && <p className="text-gray-400">Area: {size.width.toFixed(1)} x {size.height.toFixed(1)} km</p>}

                    {(mode === 'bi_temporal' ? [0, 1] : [0]).map((i) => (
                        <div key={i} className="grid grid-cols-2 gap-2">
                            <label className="text-gray-400">{mode === 'bi_temporal' ? `Date ${i + 1}: from` : 'From'}
                                <input type="date" value={ranges[i][0]} onChange={(e) => setRange(i, 0, e.target.value)} className={`${inputClass} mt-1`} />
                            </label>
                            <label className="text-gray-400">to
                                <input type="date" value={ranges[i][1]} onChange={(e) => setRange(i, 1, e.target.value)} className={`${inputClass} mt-1`} />
                            </label>
                        </div>
                    ))}

                    {problems.length > 0 && !notConfigured && (
                        <ul className="list-disc pl-5 text-gray-400">{problems.map((p) => <li key={p}>{p}</li>)}</ul>
                    )}
                    {notConfigured && (
                        <p role="note" className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-amber-200">
                            {status.reason || 'Earth Engine not configured — use samples/ or upload GeoTIFFs.'}
                        </p>
                    )}
                    <button type="button" onClick={submit} disabled={!status || notConfigured || disabled || busy || problems.length > 0}
                        className="flex w-full items-center justify-center gap-2 rounded-full bg-white px-5 py-2 text-sm font-medium text-primary transition-colors hover:bg-soft-stone disabled:cursor-not-allowed disabled:opacity-40">
                        <FiCloud /> {busy ? 'Fetching from Earth Engine (30-120 s)...' : 'Fetch from Earth Engine'}
                    </button>
                    {error && <p role="alert" className="rounded-lg border border-red-500/50 bg-red-500/10 px-3 py-2 text-red-200">{error}</p>}
                </div>
            )}
        </div>
    );
};

export default GeeFetch;
