"use client";
import useSWR from "swr";

/**
 * Live-polling read keyed by a stable string so SWR dedupes identical reads
 * across panels (client-swr-dedup). `null` key disables the fetch.
 */
export function useLive<T>(
  key: string | null,
  fetcher: () => Promise<T>,
  refreshInterval = 1500,
): T | null {
  const { data } = useSWR<T>(key, fetcher, {
    refreshInterval,
    revalidateOnFocus: true,
    keepPreviousData: true,
  });
  return data ?? null;
}
