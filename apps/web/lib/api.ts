// Typed API client. Owner: Lead (E1). Everyone calls the API through this; never write fetch URLs by hand.
//
//   const { data, error } = await api.GET("/api/v1/categories");
//
// Paths include /api/v1 (they come straight from the API's OpenAPI document), so the
// base URL is only the API's origin.
import createClient from "openapi-fetch";
import type { paths } from "./api-types";

export const API_ORIGIN = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = createClient<paths>({ baseUrl: API_ORIGIN });
