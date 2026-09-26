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

// --- Upload-based flow -------------------------------------------------------------

/** Absolute URL for a path the API returns (e.g. "/api/uploads/<id>/preview/1"). */
export const apiUrl = (path) => new URL(path, API_BASE_URL).toString();

/** POST /uploads. Resolves with {ok, status, body}; rejections (422/413) are not thrown. */
export const createUpload = async (formData) => {
    const response = await axios.post(`${API_BASE_URL}/uploads`, formData, {
        validateStatus: (s) => s === 201 || s === 413 || s === 422,
    });
    return { ok: response.status === 201, status: response.status, body: response.data };
};

export const askQuestion = async (uploadId, question, params) => {
    const response = await axios.post(`${API_BASE_URL}/query`, {
        upload_id: uploadId,
        question,
        ...(params ? { params } : {}),
    });
    return response.data;
};

export const fetchGeeStatus = async () => {
    const response = await axios.get(`${API_BASE_URL}/gee/status`);
    return response.data;
};

/** POST /gee/fetch -> accepted upload manifest (errors are thrown; use describeError). */
export const geeFetch = async (mode, bbox, dateRanges) => {
    const response = await axios.post(`${API_BASE_URL}/gee/fetch`, { mode, bbox, date_ranges: dateRanges });
    return response.data;
};

export const fetchTools = async () => {
    const response = await axios.get(`${API_BASE_URL}/tools`);
    return response.data.tools;
};

/** Fetch an evidence image as a data: URL (for self-contained HTML reports). */
export const fetchAsDataUrl = async (path) => {
    const response = await axios.get(apiUrl(path), { responseType: 'blob' });
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(response.data);
    });
};

/** Human-readable message for a failed API call (never thrown to the user as an alert). */
export const describeError = (error) => {
    if (error?.response) {
        const detail = error.response.data?.detail;
        const text = Array.isArray(detail) ? detail.map((d) => d.msg).join('; ') : detail;
        return `API error ${error.response.status}${text ? `: ${text}` : ''}`;
    }
    if (error?.request) return `Could not reach the API at ${API_BASE_URL}. Is the backend running?`;
    return error?.message || 'Unexpected error';
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
