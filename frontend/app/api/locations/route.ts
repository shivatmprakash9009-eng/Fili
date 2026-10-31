import { getCountries, getStatesOfCountry, getCitiesOfState } from "@countrystatecity/countries";
import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const level = searchParams.get("level");
  try {
    if (level === "countries") {
      const countries = await getCountries();
      return NextResponse.json(countries.map(({ name, iso2, emoji }) => ({ name, code: iso2, emoji })));
    }
    if (level === "states") {
      const country = (searchParams.get("country") || "").toUpperCase();
      if (!/^[A-Z]{2}$/.test(country)) return NextResponse.json({ error: "A valid country code is required." }, { status: 400 });
      const states = await getStatesOfCountry(country);
      return NextResponse.json(states.map(({ name, iso2 }) => ({ name, code: iso2 })));
    }
    if (level === "cities") {
      const country = (searchParams.get("country") || "").toUpperCase();
      const state = (searchParams.get("state") || "").toUpperCase();
      if (!/^[A-Z]{2}$/.test(country) || !state) return NextResponse.json({ error: "A country and state are required." }, { status: 400 });
      const cities = await getCitiesOfState(country, state);
      return NextResponse.json(cities.map(({ name }) => ({ name })).sort((a, b) => a.name.localeCompare(b.name)));
    }
    return NextResponse.json({ error: "Unsupported location level." }, { status: 400 });
  } catch {
    return NextResponse.json({ error: "Location data is temporarily unavailable." }, { status: 503 });
  }
}
