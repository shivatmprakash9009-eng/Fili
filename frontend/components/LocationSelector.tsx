"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { getCountries, getStatesOfCountry, getCitiesOfState } from "@countrystatecity/countries-browser";
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
  const [loadingCountries, setLoadingCountries] = useState(true);
  const [loadingStates, setLoadingStates] = useState(false);
  const [loadingCities, setLoadingCities] = useState(false);
  const [error, setError] = useState("");
  const stateRequestId = useRef(0);
  const cityRequestId = useRef(0);

  useEffect(() => {
    let active = true;
    getCountries()
      .then(data => {
        if (active) {
          setCountries(data.map(({ name, iso2, emoji }) => ({ name, code: iso2, emoji })));
        }
      })
      .catch(() => {
        if (active) setError("Country data could not be loaded. Check your connection and retry.");
      })
      .finally(() => {
        if (active) setLoadingCountries(false);
      });
    return () => { active = false; };
  }, []);

  const filteredCities = useMemo(() => {
    const term = citySearch.trim().toLowerCase();
    return term ? cities.filter(item => item.name.toLowerCase().includes(term)) : cities;
  }, [cities, citySearch]);

  const update = (nextCountry: string, nextState: string, nextCity: string) => {
    const country = countries.find(item => item.code === nextCountry);
    const state = states.find(item => item.code === nextState);
    if (!country || !state || !nextCity) {
      onChange(null);
      return;
    }
    onChange({
      country: country.name,
      country_code: nextCountry,
      state: state.name,
      state_code: nextState,
      city: nextCity,
    });
  };

  const handleCountryChange = (nextCountry: string) => {
    setCountryCode(nextCountry);
    setStateCode("");
    setCity("");
    setCitySearch("");
    setStates([]);
    setCities([]);
    onChange(null);
    setError("");
    cityRequestId.current += 1;

    const requestId = ++stateRequestId.current;
    if (!nextCountry) {
      setLoadingStates(false);
      return;
    }

    setLoadingStates(true);
    void getStatesOfCountry(nextCountry)
      .then(data => {
        if (requestId === stateRequestId.current) {
          setStates(data.map(({ name, iso2 }) => ({ name, code: iso2 })));
        }
      })
      .catch(() => {
        if (requestId === stateRequestId.current) {
          setError("States could not be loaded. Please select the country again to retry.");
        }
      })
      .finally(() => {
        if (requestId === stateRequestId.current) setLoadingStates(false);
      });
  };

  const handleStateChange = (nextState: string) => {
    setStateCode(nextState);
    setCity("");
    setCitySearch("");
    setCities([]);
    onChange(null);
    setError("");

    const requestId = ++cityRequestId.current;
    if (!countryCode || !nextState) {
      setLoadingCities(false);
      return;
    }

    setLoadingCities(true);
    void getCitiesOfState(countryCode, nextState)
      .then(data => {
        if (requestId === cityRequestId.current) {
          setCities(data.map(({ name }) => ({ name })).sort((a, b) => a.name.localeCompare(b.name)));
        }
      })
      .catch(() => {
        if (requestId === cityRequestId.current) {
          setError("Cities could not be loaded. Please select the state again to retry.");
        }
      })
      .finally(() => {
        if (requestId === cityRequestId.current) setLoadingCities(false);
      });
  };

  const retryCountries = () => {
    setLoadingCountries(true);
    setError("");
    getCountries()
      .then(data => setCountries(data.map(({ name, iso2, emoji }) => ({ name, code: iso2, emoji }))))
      .catch(() => setError("Country data could not be loaded. Check your connection and retry."))
      .finally(() => setLoadingCountries(false));
  };

  return (
    <div className="location-selector">
      <div className="location-selector-heading"><MapPin size={14}/><span>SEARCH AREA</span><small>Country → State → City</small></div>
      <div className="form-grid location-grid">
        <label className="field-group">
          <span>Country</span>
          <select value={countryCode} disabled={loadingCountries} onChange={event => handleCountryChange(event.target.value)} required>
            <option value="">{loadingCountries ? "Loading countries…" : "Select country"}</option>
            {countries.map(item => <option key={item.code} value={item.code}>{item.emoji ? item.emoji + " " : ""}{item.name}</option>)}
          </select>
        </label>
        <label className="field-group">
          <span>State / Province</span>
          <select value={stateCode} disabled={!countryCode || loadingStates} onChange={event => handleStateChange(event.target.value)} required>
            <option value="">{loadingStates ? "Loading states…" : "Select state"}</option>
            {states.map(item => <option key={item.code} value={item.code}>{item.name}</option>)}
          </select>
        </label>
      </div>
      <label className="field-group">
        <span>City</span>
        <input
          value={citySearch}
          disabled={!stateCode || loadingCities}
          onChange={event => { setCitySearch(event.target.value); setCity(""); onChange(null); }}
          placeholder={loadingCities ? "Loading cities…" : stateCode ? "Search city name…" : "Select a state first"}
          list="fili-city-options"
          autoComplete="off"
        />
        <datalist id="fili-city-options">
          {filteredCities.slice(0, 80).map((item, index) => <option key={item.name + index} value={item.name}/>)}
        </datalist>
        <select value={city} disabled={!stateCode || loadingCities} onChange={event => {
          setCity(event.target.value);
          update(countryCode, stateCode, event.target.value);
        }} required>
          <option value="">Choose a city from the list</option>
          {filteredCities.map((item, index) => <option key={item.name + index} value={item.name}>{item.name}</option>)}
        </select>
      </label>
      {(loadingCountries || loadingStates || loadingCities) && (
        <span className="location-loading"><LoaderCircle size={13} className="spin"/> Loading location data…</span>
      )}
      {error && (
        <div className="form-error" role="alert">
          {error}{" "}
          {!countries.length && <button type="button" onClick={retryCountries}>Retry</button>}
        </div>
      )}
      {value && <div className="location-confirmation"><MapPin size={13}/>{value.city}, {value.state}, {value.country}</div>}
    </div>
  );
}
