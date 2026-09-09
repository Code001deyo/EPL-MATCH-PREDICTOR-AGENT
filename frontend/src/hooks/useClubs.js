import { useEffect, useState } from "react";
import axios from "axios";
import API from "../config";

/* Club identity, fetched once and shared.
 *
 * `/clubs` changes when clubs are promoted, so once a season. Fetching it per
 * component would mean a request for every table, chart key and fixture list on
 * the page; the promise is cached at module scope instead, so the first
 * component to ask triggers the request and everything else joins it.
 *
 * A failure resolves to an empty map rather than rejecting. A missing badge must
 * degrade to the drawn monogram, not take the page down with it.
 */
let pending = null;

function load() {
  if (!pending) {
    pending = axios
      .get(`${API}/clubs`)
      .then(({ data }) => {
        const byName = {};
        for (const club of data.clubs || []) {
          byName[club.short_name] = club;
        }
        return byName;
      })
      .catch(() => ({}));
  }
  return pending;
}

export default function useClubs() {
  const [clubs, setClubs] = useState({});

  useEffect(() => {
    let live = true;
    load().then((byName) => live && setClubs(byName));
    return () => {
      live = false;
    };
  }, []);

  return clubs;
}
