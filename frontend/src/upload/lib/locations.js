// State / district dropdown helpers (pure, tested with node --test).

/**
 * Options for the "District / City" dropdown: major cities first (capital + biggest), then all
 * districts alphabetically. Every option's value is a district name from ``areas``; major-city
 * entries whose district is not in ``areas`` are dropped.
 */
export function districtGroups(areas = [], majorCities = []) {
    const known = new Set(areas);
    const major = (majorCities || [])
        .filter((m) => known.has(m.district))
        .map((m) => ({ label: m.label, value: m.district }));
    const all = [...areas].sort((a, b) => a.localeCompare(b)).map((a) => ({ label: a, value: a }));
    return { major, all };
}
