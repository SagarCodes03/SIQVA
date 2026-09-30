# src/fetcher.py
# Live ARGO data fetching from Argovis API using argopy
# No database, no hardcoded data — everything is fetched live.

import logging
from typing import List, Optional, Union

import argopy
import pandas as pd

from config.settings import (
    MAX_DEPTH_DBAR,
    MIN_LAT,
    MAX_LAT,
    MIN_LON,
    MAX_LON,
)


logger = logging.getLogger(__name__)


class ArgoFetcher:
    """
    Fetch live ARGO data from Argovis using argopy.

    Supported operations:
        - fetch_by_region()
        - fetch_by_float()
        - fetch_profile()

    Returned data is normalized into a Pandas DataFrame.
    """

    def __init__(self):
        """Initialize the Argovis-backed fetcher."""
        self.product = "argovis"

        logger.debug(
            "ArgoFetcher initialized with product: %s",
            self.product,
        )

    # ------------------------------------------------------------------
    # REGION
    # ------------------------------------------------------------------

    def fetch_by_region(
        self,
        lon_min: float,
        lon_max: float,
        lat_min: float,
        lat_max: float,
        depth_min: float = 0,
        depth_max: float = MAX_DEPTH_DBAR,
        date_start: str = "2020-01",
        date_end: str = "2024-12",
    ) -> pd.DataFrame:
        """
        Fetch ARGO measurements within a geographic and temporal region.

        Args:
            lon_min: Minimum longitude (-180 to 180).
            lon_max: Maximum longitude (-180 to 180).
            lat_min: Minimum latitude (-90 to 90).
            lat_max: Maximum latitude (-90 to 90).

            depth_min:
                Minimum pressure/depth in dbar.

            depth_max:
                Maximum pressure/depth in dbar.

            date_start:
                Start month in YYYY-MM format.

            date_end:
                End month in YYYY-MM format, inclusive.

        Returns:
            DataFrame containing ARGO measurements.

        Raises:
            ValueError:
                Invalid coordinates, depth, dates, or no data.

            ConnectionError:
                Argovis/argopy request failure.
        """

        # Validate input
        self._validate_coordinates(
            lon_min,
            lon_max,
            lat_min,
            lat_max,
        )

        self._validate_depths(
            depth_min,
            depth_max,
        )

        start_date, end_date = self._normalize_date_range(
            date_start,
            date_end,
        )

        logger.info(
            "Fetching ARGO region: "
            "lon=[%.2f, %.2f], "
            "lat=[%.2f, %.2f], "
            "depth=[%.1f, %.1f], "
            "dates=[%s, %s)",
            lon_min,
            lon_max,
            lat_min,
            lat_max,
            depth_min,
            depth_max,
            start_date,
            end_date,
        )

        try:
            # Current argopy API
            fetcher = argopy.DataFetcher(
                product=self.product
            )

            df = (
                fetcher
                .region([
                    lon_min,
                    lon_max,
                    lat_min,
                    lat_max,
                    depth_min,
                    depth_max,
                    start_date,
                    end_date,
                ])
                .to_dataframe()
            )

            df = self._normalize_dataframe(df)

            if df.empty:
                raise ValueError(
                    "No ARGO data found for the "
                    "requested region and date range."
                )

            logger.info(
                "Fetched %d ARGO measurements",
                len(df),
            )

            return df

        except argopy.errors.DataNotFound as exc:
            logger.warning(
                "No ARGO data found for region: %s",
                exc,
            )

            raise ValueError(
                "No ARGO data found for the "
                "requested region/date range."
            ) from exc

        except ValueError:
            raise

        except Exception as exc:
            logger.exception(
                "Argovis region request failed"
            )

            raise ConnectionError(
                f"Failed to fetch ARGO region data "
                f"from Argovis: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # FLOAT
    # ------------------------------------------------------------------

    def fetch_by_float(
        self,
        wmo_ids: Union[int, List[int]],
        date_start: Optional[str] = None,
        date_end: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Fetch ARGO measurements for one or more WMO float IDs.

        Args:
            wmo_ids:
                Single WMO ID or list of WMO IDs.

            date_start:
                Optional start month in YYYY-MM format.

            date_end:
                Optional end month in YYYY-MM format, inclusive.

        Returns:
            DataFrame containing ARGO measurements.
        """

        wmo_ids = self._normalize_wmo_ids(
            wmo_ids
        )

        if date_start or date_end:
            start_date, end_date = (
                self._normalize_date_range(
                    date_start,
                    date_end,
                )
            )
        else:
            start_date = None
            end_date = None

        logger.info(
            "Fetching ARGO float(s): %s",
            wmo_ids,
        )

        try:
            fetcher = argopy.DataFetcher(
                product=self.product
            )

            df = (
                fetcher
                .float(wmo_ids)
                .to_dataframe()
            )

            df = self._normalize_dataframe(df)

            # Float requests are fetched first and then
            # filtered locally by date.
            if start_date or end_date:
                df = self._filter_by_date(
                    df,
                    start_date,
                    end_date,
                )

            if df.empty:
                raise ValueError(
                    f"No ARGO data found for float(s) "
                    f"{wmo_ids}"
                )

            logger.info(
                "Fetched %d measurements from %d float(s)",
                len(df),
                len(wmo_ids),
            )

            return df

        except argopy.errors.DataNotFound as exc:
            logger.warning(
                "No ARGO data found for WMO IDs %s: %s",
                wmo_ids,
                exc,
            )

            raise ValueError(
                f"No ARGO data found for float(s) "
                f"{wmo_ids}"
            ) from exc

        except ValueError:
            raise

        except Exception as exc:
            logger.exception(
                "Argovis float request failed"
            )

            raise ConnectionError(
                f"Failed to fetch ARGO float data "
                f"from Argovis: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # PROFILE
    # ------------------------------------------------------------------

    def fetch_profile(
        self,
        wmo_id: int,
        cycle_number: int,
    ) -> pd.DataFrame:
        """
        Fetch a single ARGO profile.

        Args:
            wmo_id:
                ARGO float WMO ID.

            cycle_number:
                ARGO cycle/profile number.

        Returns:
            DataFrame containing measurements
            from the requested profile.
        """

        self._validate_wmo_id(
            wmo_id
        )

        if not isinstance(
            cycle_number,
            int,
        ):
            raise ValueError(
                "cycle_number must be an integer"
            )

        if cycle_number < 0:
            raise ValueError(
                "cycle_number must be >= 0"
            )

        logger.info(
            "Fetching ARGO profile: "
            "WMO=%d, cycle=%d",
            wmo_id,
            cycle_number,
        )

        try:
            fetcher = argopy.DataFetcher(
                product=self.product
            )

            df = (
                fetcher
                .profile(
                    wmo_id,
                    cycle_number,
                )
                .to_dataframe()
            )

            df = self._normalize_dataframe(df)

            if df.empty:
                raise ValueError(
                    f"No data found for WMO "
                    f"{wmo_id}, cycle {cycle_number}"
                )

            logger.info(
                "Fetched %d measurements "
                "for WMO=%d cycle=%d",
                len(df),
                wmo_id,
                cycle_number,
            )

            return df

        except argopy.errors.DataNotFound as exc:
            logger.warning(
                "Profile not found: "
                "WMO=%d, cycle=%d",
                wmo_id,
                cycle_number,
            )

            raise ValueError(
                f"Profile not found for WMO "
                f"{wmo_id}, cycle {cycle_number}"
            ) from exc

        except ValueError:
            raise

        except Exception as exc:
            logger.exception(
                "Argovis profile request failed"
            )

            raise ConnectionError(
                f"Failed to fetch ARGO profile "
                f"from Argovis: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # DATAFRAME NORMALIZATION
    # ------------------------------------------------------------------

    def _normalize_dataframe(
        self,
        df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Normalize raw argopy output.

        Original ARGO column names are preserved.

        Additional convenient aliases are added:

            PLATFORM_NUMBER -> WMO
            CYCLE_NUMBER    -> CYCLE
            LATITUDE        -> LAT
            LONGITUDE       -> LON
        """

        if not isinstance(
            df,
            pd.DataFrame,
        ):
            raise TypeError(
                "Expected argopy to return "
                "a pandas DataFrame"
            )

        df = df.copy()

        # Remove existing DataFrame index.
        df.reset_index(
            drop=True,
            inplace=True,
        )

        # Normalize timestamps to UTC.
        if "TIME" in df.columns:
            df["TIME"] = pd.to_datetime(
                df["TIME"],
                utc=True,
                errors="coerce",
            )

        # Preserve official ARGO fields and
        # create convenient aliases.
        if "PLATFORM_NUMBER" in df.columns:
            df["WMO"] = df["PLATFORM_NUMBER"]

        if "CYCLE_NUMBER" in df.columns:
            df["CYCLE"] = df["CYCLE_NUMBER"]

        if "LATITUDE" in df.columns:
            df["LAT"] = df["LATITUDE"]

        if "LONGITUDE" in df.columns:
            df["LON"] = df["LONGITUDE"]

        # Required fields for Sequa.
        required_columns = [
            "PRES",
            "TEMP",
            "PSAL",
            "LAT",
            "LON",
            "TIME",
            "WMO",
        ]

        missing = [
            column
            for column in required_columns
            if column not in df.columns
        ]

        if missing:
            raise ValueError(
                "ARGO response is missing "
                "required columns: "
                + ", ".join(missing)
            )

        return df

    # ------------------------------------------------------------------
    # DATE FILTERING
    # ------------------------------------------------------------------

    def _filter_by_date(
        self,
        df: pd.DataFrame,
        date_start: Optional[str],
        date_end: Optional[str],
    ) -> pd.DataFrame:
        """
        Filter measurements using an inclusive
        month-based date range.

        Example:

            date_start = "2024-01"
            date_end   = "2024-03"

        means:

            TIME >= 2024-01-01
            TIME <  2024-04-01
        """

        if "TIME" not in df.columns:
            raise ValueError(
                "Cannot filter by date: "
                "TIME column is missing"
            )

        df = df.copy()

        df["TIME"] = pd.to_datetime(
            df["TIME"],
            utc=True,
            errors="coerce",
        )

        if date_start:
            start = pd.Timestamp(
                date_start,
                tz="UTC",
            )

            df = df[
                df["TIME"] >= start
            ]

        if date_end:
            end = (
                pd.Timestamp(
                    date_end,
                    tz="UTC",
                )
                + pd.offsets.MonthBegin(1)
            )

            df = df[
                df["TIME"] < end
            ]

        return df.reset_index(
            drop=True
        )

    # ------------------------------------------------------------------
    # VALIDATION
    # ------------------------------------------------------------------

    def _validate_coordinates(
        self,
        lon_min: float,
        lon_max: float,
        lat_min: float,
        lat_max: float,
    ) -> None:
        """Validate geographic coordinates."""

        if not (
            MIN_LON <= lon_min <= MAX_LON
            and MIN_LON <= lon_max <= MAX_LON
        ):
            raise ValueError(
                f"Longitude must be between "
                f"{MIN_LON} and {MAX_LON}"
            )

        if not (
            MIN_LAT <= lat_min <= MAX_LAT
            and MIN_LAT <= lat_max <= MAX_LAT
        ):
            raise ValueError(
                f"Latitude must be between "
                f"{MIN_LAT} and {MAX_LAT}"
            )

        if lon_min >= lon_max:
            raise ValueError(
                "lon_min must be less than lon_max"
            )

        if lat_min >= lat_max:
            raise ValueError(
                "lat_min must be less than lat_max"
            )

    def _validate_depths(
        self,
        depth_min: float,
        depth_max: float,
    ) -> None:
        """Validate pressure/depth limits."""

        if depth_min < 0:
            raise ValueError(
                "depth_min must be >= 0"
            )

        if depth_max < 0:
            raise ValueError(
                "depth_max must be >= 0"
            )

        if depth_min >= depth_max:
            raise ValueError(
                "depth_min must be less than depth_max"
            )

    def _validate_wmo_id(
        self,
        wmo_id: int,
    ) -> None:
        """Validate a single WMO ID."""

        if not isinstance(
            wmo_id,
            int,
        ):
            raise ValueError(
                "WMO ID must be an integer, "
                f"got {type(wmo_id).__name__}"
            )

        if wmo_id <= 0:
            raise ValueError(
                "WMO ID must be positive"
            )

    def _normalize_wmo_ids(
        self,
        wmo_ids: Union[int, List[int]],
    ) -> List[int]:
        """Normalize and validate WMO IDs."""

        if isinstance(
            wmo_ids,
            int,
        ):
            wmo_ids = [wmo_ids]

        if not isinstance(
            wmo_ids,
            list,
        ):
            raise ValueError(
                "wmo_ids must be an integer "
                "or list of integers"
            )

        if not wmo_ids:
            raise ValueError(
                "At least one WMO ID is required"
            )

        for wmo_id in wmo_ids:
            self._validate_wmo_id(
                wmo_id
            )

        # Remove duplicates while
        # preserving original order.
        return list(
            dict.fromkeys(wmo_ids)
        )

    def _normalize_date_range(
        self,
        date_start: Optional[str],
        date_end: Optional[str],
    ) -> tuple[str, str]:
        """
        Normalize YYYY-MM dates.

        Returns:

            start_date
            exclusive_end_date

        Example:

            2024-01, 2024-03

        becomes:

            2024-01-01
            2024-04-01
        """

        if not date_start:
            start = pd.Timestamp(
                "1900-01-01"
            )
        else:
            start = pd.to_datetime(
                date_start,
                format="%Y-%m",
                errors="raise",
            )

        if not date_end:
            end = pd.Timestamp(
                "2100-01-01"
            )
        else:
            end = pd.to_datetime(
                date_end,
                format="%Y-%m",
                errors="raise",
            )

        if start > end:
            raise ValueError(
                "date_start must be before "
                "or equal to date_end"
            )

        # Inclusive end month -> exclusive
        # first day of the following month.
        exclusive_end = (
            end + pd.offsets.MonthBegin(1)
        )

        return (
            start.strftime("%Y-%m-%d"),
            exclusive_end.strftime("%Y-%m-%d"),
        )


# ----------------------------------------------------------------------
# Convenience functions
# ----------------------------------------------------------------------

def fetch_region(
    lon_min: float,
    lon_max: float,
    lat_min: float,
    lat_max: float,
    **kwargs,
) -> pd.DataFrame:
    """
    Convenience wrapper for regional ARGO fetching.
    """

    return ArgoFetcher().fetch_by_region(
        lon_min,
        lon_max,
        lat_min,
        lat_max,
        **kwargs,
    )


def fetch_float(
    wmo_ids: Union[int, List[int]],
    **kwargs,
) -> pd.DataFrame:
    """
    Convenience wrapper for ARGO float fetching.
    """

    return ArgoFetcher().fetch_by_float(
        wmo_ids,
        **kwargs,
    )