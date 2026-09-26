import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import Hero from './components/Hero';
import Sidebar from './components/Sidebar';
import MapComponent from './components/MapComponent';
import ResultsPanel from './components/ResultsPanel';
import UploadAnalysis from './upload/UploadAnalysis';
import { fetchStates, fetchAreas, fetchLocation, fetchSentinelInfo, runAnalysis } from './api';

function App() {
    const [states, setStates] = useState([]);
    const [selectedState, setSelectedState] = useState('');
    const [areas, setAreas] = useState([]);
    const [majorCities, setMajorCities] = useState([]);
    const [selectedArea, setSelectedArea] = useState('');
    const [query, setQuery] = useState('');

    const [geometry, setGeometry] = useState(null);
    const [sentinelData, setSentinelData] = useState(null);
    const [analysisResult, setAnalysisResult] = useState(null);
    const [loadingMessage, setLoadingMessage] = useState('');
    const [flyToLocation, setFlyToLocation] = useState(null);

    // "map" = the original Earth Engine flow, "upload" = the upload-based agent flow.
    // The map view stays mounted (only hidden) so its state and drawn AOI survive tab switches.
    const [view, setView] = useState('map');
    const [uploadOpened, setUploadOpened] = useState(false);
    const changeView = (next) => {
        setView(next);
        if (next === 'upload') setUploadOpened(true);
        // Leaflet measures its container on resize; nudge it after being un-hidden.
        if (next === 'map') setTimeout(() => window.dispatchEvent(new Event('resize')), 0);
    };

    useEffect(() => {
        fetchStates().then(data => setStates(data.states || []));
    }, []);

    useEffect(() => {
        let stale = false;
        setAreas([]);
        setMajorCities([]);
        if (selectedState) {
            fetchAreas(selectedState).then(data => {
                if (stale) return;  // the user already picked another state
                setAreas(data.areas || []);
                setMajorCities(data.major_cities || []);
            });
        }
        return () => { stale = true; };
    }, [selectedState]);

    const handleStateChange = (e) => {
        // Reset area in the same batch as the state change so no effect
        // ever observes a (newState, oldArea) combination.
        setSelectedState(e.target.value);
        setSelectedArea('');
    };

    // Picking a district flies the map there (the Explore Area button still works too).
    const handleAreaChange = async (e) => {
        const area = e.target.value;
        setSelectedArea(area);
        if (!selectedState || !area) return;
        try {
            setFlyToLocation(await fetchLocation(selectedState, area));
        } catch (error) {
            console.error(error);
        }
    };

    const handleGeometryChange = (geom) => {
        setGeometry(geom);
        setSentinelData(null);
        setAnalysisResult(null);
    };

    const handleExploreArea = async () => {
        if (!selectedState || !selectedArea) return;
        try {
            const loc = await fetchLocation(selectedState, selectedArea);
            setFlyToLocation(loc);
        } catch (error) {
            console.error(error);
            alert('Unable to locate that area.');
        }
    };

    const runAnalysisFlow = async (targetQuery) => {
        if (!selectedState || !selectedArea || !geometry || !targetQuery) {
            alert('Select a state, area, draw an AOI on the map, and pick a question first.');
            return;
        }
        setLoadingMessage('Fetching Sentinel-2 imagery and validating landcover...');
        try {
            const sentinel = await fetchSentinelInfo(selectedState, selectedArea, geometry);
            setSentinelData(sentinel);

            setLoadingMessage('Analyzing spectral data...');
            const result = await runAnalysis(selectedState, selectedArea, geometry, targetQuery);
            setAnalysisResult(result);
        } catch (error) {
            console.error(error);
            alert('Analysis could not be completed.');
        } finally {
            setLoadingMessage('');
        }
    };

    const handleAnalyze = () => runAnalysisFlow(query);

    const handleSelectFeature = (featureQuery) => {
        setQuery(featureQuery);
        document.getElementById('explore')?.scrollIntoView({ behavior: 'smooth' });
    };

    // Map's NDVI/NDWI/Flood tabs map onto a specific suggested question; clicking
    // one should just work, whether or not that exact analysis has run yet.
    const TAB_QUERY = {
        NDVI: 'Where is the vegetation?',
        NDWI: 'Where are the water bodies?',
        'Potential Flood Proxy': 'Which regions are potentially flooded?',
    };

    const handleRequestLayer = (tabKey) => {
        const mappedQuery = TAB_QUERY[tabKey];
        if (!mappedQuery) return;
        setQuery(mappedQuery);
        if (selectedState && selectedArea && geometry) {
            runAnalysisFlow(mappedQuery);
        } else {
            alert('Select a state, area, and draw an AOI on the map first — this layer will then run automatically.');
        }
    };

    const canAnalyze = Boolean(selectedState && selectedArea && geometry && query);

    return (
        <div className="h-screen w-screen overflow-y-auto overflow-x-hidden bg-space-900">
            <Header view={view} onViewChange={changeView} />
            <div className={view === 'map' ? '' : 'hidden'}>
            <Hero
                onStartExploring={() => document.getElementById('explore')?.scrollIntoView({ behavior: 'smooth' })}
                onSelectFeature={handleSelectFeature}
            />

            <section id="explore" className="relative flex flex-row h-[850px] max-h-[85vh] w-full overflow-hidden">
                <Sidebar
                    states={states}
                    selectedState={selectedState}
                    onStateChange={handleStateChange}
                    areas={areas}
                    selectedArea={selectedArea}
                    onAreaChange={handleAreaChange}
                    majorCities={majorCities}
                    onExploreArea={handleExploreArea}
                    query={query}
                    onQuerySelect={setQuery}
                    onAnalyze={handleAnalyze}
                    canAnalyze={canAnalyze}
                    landcoverWarning={sentinelData?.landcover?.warning ? sentinelData.landcover.message : null}
                />

                <div className="relative flex-1 w-1/2 h-full p-4">
                    {loadingMessage && (
                        <div className="absolute top-20 left-1/2 -translate-x-1/2 z-[1000] flex items-center gap-3 rounded-full border border-accent-cyan/40 bg-space-800/80 px-6 py-3 text-sm font-medium text-white backdrop-blur-md">
                            <div className="w-4 h-4 border-2 border-accent-cyan border-t-transparent rounded-full animate-spin"></div>
                            {loadingMessage}
                        </div>
                    )}

                    <div className="h-full w-full overflow-hidden rounded-lg ring-1 ring-white/[0.07]">
                        <MapComponent
                            onGeometryChange={handleGeometryChange}
                            sentinelTileUrl={sentinelData?.tile_url}
                            analysisTileUrl={analysisResult?.tile_url}
                            analysisIndex={analysisResult?.index}
                            flyToLocation={flyToLocation}
                            onRequestLayer={handleRequestLayer}
                        />
                    </div>
                </div>

                <ResultsPanel
                    selectedState={selectedState}
                    selectedArea={selectedArea}
                    query={query}
                    sentinelData={sentinelData}
                    analysisResult={analysisResult}
                />
            </section>
            </div>

            {uploadOpened && (
                <div className={view === 'upload' ? '' : 'hidden'}>
                    <UploadAnalysis />
                </div>
            )}
        </div>
    );
}

export default App;
