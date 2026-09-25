import axios from 'axios';

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

export const fetchStates = async () => {
    const response = await axios.get(`${API_BASE_URL}/states`);
    return response.data;
};

export const fetchAreas = async (state) => {
    const response = await axios.get(`${API_BASE_URL}/areas/${state}`);
    return response.data;
};

export const fetchLocation = async (state, area) => {
    const response = await axios.get(`${API_BASE_URL}/location/${encodeURIComponent(state)}/${encodeURIComponent(area)}`);
    return response.data;
};

export const fetchSentinelInfo = async (state, area, geometry) => {
    const response = await axios.post(`${API_BASE_URL}/sentinel`, {
        state,
        area,
        geometry
    });
    return response.data;
};

export const runAnalysis = async (state, area, geometry, query) => {
    const response = await axios.post(`${API_BASE_URL}/analyze`, {
        state,
        area,
        geometry,
        query
    });
    return response.data;
};
