"use client";

import { useEffect, useMemo, useState } from "react";
import { LoaderCircle, MapPin } from "lucide-react";

type PlaceOption = { name: string; code?: string; emoji?: string };

type LocationScope = {
  country: string;
  country_code: string;
  state: string;
  state_code: string;
  city: string;
};

export default function LocationSelector({ value, onChange }: {
  value: LocationScope | null;
  onChange: (value: LocationScope | null) => void;
}) {
  const [countries, setCountries] = useState<PlaceOption[]>([]);
  const [states, setStates] = useState<PlaceOption[]>([]);
  const [cities, setCities] = useState<PlaceOption[]>([]);
  const [countryCode, setCountryCode] = useState(value?.country_code || "");
  const [stateCode, setStateCode] = useState(value?.state_code || "");
  const [city, setCity] = useState(value?.city || "");
  const [citySearch, setCitySearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    fetch("/api/locations?level=countries").then(async response => {
      if (!response.ok) throw new Error("Could not load countries.");
      return response.json();
    }).then(data => { if (active) setCountries(data); })
      .catch(() => { if (active) setError("Location data could not be loaded. Refresh and try again."); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!countryCode) return;
    let active = true;
    setLoading(true);
    fetch("/api/locations?level=states&country=" + encodeURIComponent(countryCode))
      .then(async response => { if (!response.ok) throw new Error(); return response.json(); })
      .then(data => { if (active) setStates(data); })
      .catch(() => { if (active) setError("States could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [countryCode]);

  useEffect(() => {
    if (!countryCode || !stateCode) return;
    let active = true;
    setLoading(true);
    fetch("/api/locations?level=cities&country=" + encodeURIComponent(countryCode) + "&state=" + encodeURIComponent(stateCode))
      .then(async response => { if (!response.ok) throw new Error(); return response.json(); })
      .then(data => { if (active) setCities(data); })
      .catch(() => { if (active) setError("Cities could not be loaded."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [countryCode, stateCode]);

  const filteredCities = useMemo(() => {
    const term = citySearch.trim().toLowerCase();
    return term ? cities.filter(item => item.name.toLowerCase().includes(term)) : cities;
  }, [cities, citySearch]);

  const update = (nextCountry: string, nextState: string, nextCity: string) => {
    const country = countries.find(item => item.code === nextCountry);
    const state = states.find(item => item.code === nextState);
    if (!country || !state || !nextCity) { onChange(null); return; }
    onChange({ country: country.name, country_code: nextCountry, state: state.name, state_code: nextState, city: nextCity });
  };

  return (
    <div className="location-selector">
      <div className="location-selector-heading"><MapPin size={14}/><span>SEARCH AREA</span><small>Country → State → City</small></div>
      <div className="form-grid location-grid">
        <label className="field-group">
          <span>Country</span>
          <select value={countryCode} onChange={event => {
            const next = event.target.value; setCountryCode(next); setStates([]); setStateCode(""); setCities([]); setCity(""); setCitySearch(""); setError(""); onChange(null);
          }} required>
            <option value="">Select country</option>
            {countries.map(item => <option key={item.code} value={item.code}>{item.emoji ? item.emoji + " " : ""}{item.name}</option>)}
          </select>
        </label>
        <label className="field-group">
          <span>State / Province</span>
          <select value={stateCode} disabled={!countryCode || loading} onChange={event => {
            const next = event.target.value; setStateCode(next); setCities([]); setCity(""); setCitySearch(""); setError(""); onChange(null);
          }} required>
            <option value="">Select state</option>
            {states.map(item => <option key={item.code} value={item.code}>{item.name}</option>)}
          </select>
        </label>
      </div>
      <label className="field-group">
        <span>City</span>
        <input value={citySearch} disabled={!stateCode} onChange={event => { setCitySearch(event.target.value); setCity(""); onChange(null); }}
          placeholder={stateCode ? "Search city name…" : "Select a state first"} list="fili-city-options" autoComplete="off"/>
        <datalist id="fili-city-options">
          {filteredCities.slice(0, 80).map((item, index) => <option key={item.name + index} value={item.name}/>)}
        </datalist>
        <select value={city} disabled={!stateCode} onChange={event => { setCity(event.target.value); update(countryCode, stateCode, event.target.value); }} required>
          <option value="">Choose a city from the list</option>
          {filteredCities.map((item, index) => <option key={item.name + index} value={item.name}>{item.name}</option>)}
        </select>
      </label>
      {loading && <span className="location-loading"><LoaderCircle size={13} className="spin"/> Loading location data…</span>}
      {error && <span className="form-error">{error}</span>}
      {value && <div className="location-confirmation"><MapPin size={13}/>{value.city}, {value.state}, {value.country}</div>}
    </div>
  );
}
