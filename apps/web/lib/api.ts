// Typed API client. Owner: Lead (E1). Everyone calls the API through this; never write fetch URLs by hand.
import createClient from "openapi-fetch";
import type { paths } from "./api-types";

export const api = createClient<paths>({
  baseUrl: `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1`,
});
