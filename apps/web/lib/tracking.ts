// Position estimate between checkpoints. Owner: Lead (E10). Frontend 2 calls it; don't change it.
export type EstimatedPosition = { lat: number; lng: number; distance_km: number; is_estimate: boolean };
