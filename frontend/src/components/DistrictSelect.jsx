import React, { useState } from 'react';
import { districtGroups } from '../upload/lib/locations.js';

const MAJOR = 'major:';

/**
 * "District / City" dropdown: two <optgroup>s, "Major cities" (capital + biggest) then "All districts".
 * Disabled until a state is picked. Selection by dropdown only. ``onChange`` receives an event whose
 * target.value is always the district name, whichever group it was picked from.
 */
const DistrictSelect = ({ value, onChange, areas, majorCities, disabled, className, placeholder = 'Select district / city', ...rest }) => {
    const { major, all } = districtGroups(areas, majorCities);
    // Remember which group the current district was picked from, so the right label stays selected.
    const [picked, setPicked] = useState('');
    const shown = picked && picked.slice(MAJOR.length) === value && picked.startsWith(MAJOR) ? picked : value;

    const handle = (e) => {
        const raw = e.target.value;
        setPicked(raw);
        const district = raw.startsWith(MAJOR) ? raw.slice(MAJOR.length) : raw;
        onChange({ target: { value: district } });
    };

    return (
        <select value={shown || ''} onChange={handle} disabled={disabled} className={className} {...rest}>
            <option value="">{placeholder}</option>
            {major.length > 0 && (
                <optgroup label="Major cities">
                    {major.map((o) => <option key={`m-${o.value}`} value={`${MAJOR}${o.value}`}>{o.label}</option>)}
                </optgroup>
            )}
            {all.length > 0 && (
                <optgroup label="All districts">
                    {all.map((o) => <option key={`a-${o.value}`} value={o.value}>{o.label}</option>)}
                </optgroup>
            )}
        </select>
    );
};

export default DistrictSelect;
