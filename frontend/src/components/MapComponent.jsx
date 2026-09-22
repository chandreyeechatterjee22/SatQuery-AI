import React, { useRef, useEffect, useState } from 'react';
import { MapContainer, TileLayer, FeatureGroup, ZoomControl, ScaleControl, useMap } from 'react-leaflet';
import { EditControl } from 'react-leaflet-draw';
import { FiLayers, FiChevronDown } from 'react-icons/fi';
import 'leaflet/dist/leaflet.css';
import 'leaflet-draw/dist/leaflet.draw.css';

const TABS = [
    { key: 'satellite', label: 'Satellite' },
    { key: 'NDVI', label: 'NDVI' },
    { key: 'NDWI', label: 'NDWI' },
    { key: 'Potential Flood Proxy', label: 'Flood' },
];

const FlyToLocation = ({ location }) => {
    const map = useMap();

    useEffect(() => {
        if (location) {
            map.flyTo([location.lat, location.lon], location.zoom);
        }
    }, [location, map]);

    return null;
};

const MapComponent = ({ onGeometryChange, sentinelTileUrl, analysisTileUrl, analysisIndex, flyToLocation, onRequestLayer }) => {
    const featureGroupRef = useRef();
    const [baseLayer, setBaseLayer] = useState('satellite');
    const [showLabels, setShowLabels] = useState(true);
    const [activeTab, setActiveTab] = useState('satellite');
    const [opacity, setOpacity] = useState(70);
    const [layerMenuOpen, setLayerMenuOpen] = useState(false);

    // Jump straight to the freshly computed layer once an analysis finishes.
    useEffect(() => {
        if (analysisTileUrl && analysisIndex) {
            setActiveTab(analysisIndex);
        }
    }, [analysisTileUrl, analysisIndex]);

    const onCreated = (e) => {
        const { layer } = e;
        const geojson = layer.toGeoJSON().geometry;
        onGeometryChange(geojson);
    };

    const onEdited = (e) => {
        const layers = e.layers;
        layers.eachLayer((layer) => {
            const geojson = layer.toGeoJSON().geometry;
            onGeometryChange(geojson);
        });
    };

    const onDeleted = () => {
        onGeometryChange(null);
    };

    const showAnalysisOverlay = activeTab !== 'satellite' && analysisIndex === activeTab && analysisTileUrl;

    return (
        <div className="relative h-full w-full">
            {/* Map controls: one row so the two clusters can never overlap/intercept each other's clicks */}
            <div className="absolute top-4 left-4 right-4 z-[1000] flex items-start justify-between gap-2 pointer-events-none">
                <div className="pointer-events-auto flex items-center gap-1 p-1 rounded-xl bg-space-800/90 backdrop-blur-md border border-space-700/60 shadow-xl">
                    {TABS.map(tab => {
                        const isComputed = tab.key === 'satellite' || analysisIndex === tab.key;
                        return (
                            <button
                                key={tab.key}
                                title={isComputed ? '' : 'Runs this analysis on the current AOI'}
                                onClick={() => {
                                    setActiveTab(tab.key);
                                    if (!isComputed) onRequestLayer(tab.key);
                                }}
                                className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors ${
                                    activeTab === tab.key
                                        ? 'bg-accent-cyan text-space-900'
                                        : 'text-gray-300 hover:bg-space-700'
                                }`}
                            >
                                {tab.label}
                            </button>
                        );
                    })}
                </div>

                <div className="pointer-events-auto flex items-center gap-2">
                    {showAnalysisOverlay && (
                        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl bg-space-800/90 backdrop-blur-md border border-space-700/60 shadow-xl text-xs text-gray-300">
                            <span>Opacity</span>
                            <input
                                type="range"
                                min="10"
                                max="100"
                                value={opacity}
                                onChange={(e) => setOpacity(Number(e.target.value))}
                                className="w-16 accent-accent-cyan"
                            />
                            <span className="w-8 text-right">{opacity}%</span>
                        </div>
                    )}

                    <div className="relative">
                        <button
                            onClick={() => setLayerMenuOpen(o => !o)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-space-800/90 backdrop-blur-md border border-space-700/60 shadow-xl text-xs font-semibold text-gray-300 hover:text-white transition-colors"
                        >
                            <FiLayers /> Layer <FiChevronDown />
                        </button>
                        {layerMenuOpen && (
                            <div className="absolute right-0 mt-2 w-44 rounded-xl bg-space-800 border border-space-700/60 shadow-xl p-2 text-xs text-gray-300">
                                <button
                                    onClick={() => setBaseLayer('satellite')}
                                    className={`w-full text-left px-2 py-1.5 rounded-lg ${baseLayer === 'satellite' ? 'bg-accent-cyan/10 text-accent-cyan' : 'hover:bg-space-700'}`}
                                >
                                    Satellite basemap
                                </button>
                                <button
                                    onClick={() => setBaseLayer('osm')}
                                    className={`w-full text-left px-2 py-1.5 rounded-lg ${baseLayer === 'osm' ? 'bg-accent-cyan/10 text-accent-cyan' : 'hover:bg-space-700'}`}
                                >
                                    OpenStreetMap
                                </button>
                                <div className="my-1 border-t border-space-700/60" />
                                <label className="flex items-center gap-2 px-2 py-1.5 cursor-pointer">
                                    <input type="checkbox" checked={showLabels} onChange={(e) => setShowLabels(e.target.checked)} />
                                    Place labels
                                </label>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <MapContainer
                center={[20.5937, 78.9629]} // Center of India
                zoom={5}
                maxZoom={21}
                className="h-full w-full bg-space-900"
                zoomControl={false}
            >
                <FlyToLocation location={flyToLocation} />
                <ZoomControl position="bottomright" />
                <ScaleControl position="bottomleft" imperial={false} />

                {baseLayer === 'satellite' ? (
                    <TileLayer
                        attribution="Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"
                        url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                        maxZoom={21}
                        maxNativeZoom={19}
                    />
                ) : (
                    <TileLayer
                        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
                        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
                        maxZoom={21}
                        maxNativeZoom={19}
                    />
                )}

                {showLabels && baseLayer === 'satellite' && (
                    <TileLayer
                        url="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"
                        maxZoom={21}
                        maxNativeZoom={19}
                    />
                )}

                {activeTab === 'satellite' && sentinelTileUrl && (
                    <TileLayer url={sentinelTileUrl} attribution="Google Earth Engine" maxNativeZoom={16} />
                )}

                {showAnalysisOverlay && (
                    <TileLayer url={analysisTileUrl} opacity={opacity / 100} attribution="Google Earth Engine Analysis" maxNativeZoom={16} />
                )}

                <FeatureGroup ref={featureGroupRef}>
                    <EditControl
                        position="topleft"
                        onCreated={onCreated}
                        onEdited={onEdited}
                        onDeleted={onDeleted}
                        draw={{
                            rectangle: false,
                            circle: false,
                            circlemarker: false,
                            marker: false,
                            polyline: false,
                            polygon: {
                                allowIntersection: false,
                                drawError: {
                                    color: '#e1e100',
                                    message: '<strong>Oh snap!<strong> you can\'t draw that!'
                                },
                                shapeOptions: {
                                    color: '#5BC0BE'
                                }
                            }
                        }}
                    />
                </FeatureGroup>
            </MapContainer>
        </div>
    );
};

export default MapComponent;
