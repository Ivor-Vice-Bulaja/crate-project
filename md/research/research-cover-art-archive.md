# MusicBrainz Cover Art Archive (CAA) Research

Researched: 2026-04-04

All findings are derived directly from the sources listed below. Claims are traceable to
a specific source. Where something could not be confirmed from primary sources, this is
stated explicitly.

---

## Sources

- CAA API documentation: https://musicbrainz.org/doc/Cover_Art_Archive/API
- Official CAA specification: https://github.com/metabrainz/CAA-spec/blob/master/caa-specification.md
- python-musicbrainzngs caa.py: https://github.com/alastair/python-musicbrainzngs/blob/master/musicbrainzngs/caa.py
- libcoverart sample JSON: https://raw.githubusercontent.com/metabrainz/libcoverart/master/sample-json.txt
- coverart_redirect service: https://github.com/metabrainz/coverart_redirect
- MusicBrainz image types documentation: https://musicbrainz.org/doc/Cover_Art/Types
- MetaBrainz community: check-for-availability-of-release-group-cover-art
- MetaBrainz community: check-if-cover-art-is-available-via-musicbrainz-api
- Live MusicBrainz API responses: fetched directly during research session

---

## What the Cover Art Archive Is

The Cover Art Archive (CAA) is a joint project between the Internet Archive and MusicBrainz.
Images are stored on archive.org infrastructure and indexed using MusicBrainz Release MBIDs.
The community curates the collection; MusicBrainz manages the edit workflow for adding,
removing, and modifying images.

The CAA is separate from the MusicBrainz API. It has its own base URL and its own HTTP
response behaviour. Requests go to `coverartarchive.org`, not `musicbrainz.org`.

---

## Base URL

```
https://coverartarchive.org
```

HTTPS only in practice. The python-musicbrainzngs library defaults `https=True` for the
`coverartarchive.org` hostname (see `set_caa_hostname()` in caa.py).

---

## Authentication

None required. No API key, no OAuth, no token. Anonymous GET requests work.

---

## Rate Limits

The official documentation states: **"Currently no rate limiting rules in place."**

This is confirmed by the API spec. The 503 response code exists in the spec and in client
library error handling, but is not actively triggered by the live service as of this
research date. Treat this as a theoretical limit — do not rely on its continued absence.

The MusicBrainz API (musicbrainz.org) has its own rate limit (1 request/second without
a User-Agent header). That limit does not apply to coverartarchive.org.

---

## Endpoint Reference

### 1. `/release/{mbid}/`

Returns a JSON listing of all cover art for a specific release.

```
GET https://coverartarchive.org/release/{mbid}/
```

**HTTP methods:** GET, HEAD

**Response codes:**
- `307 Temporary Redirect` — release exists; redirects to the `index.json` on archive.org
- `400 Bad Request` — `{mbid}` is not a valid UUID
- `404 Not Found` — no release with this MBID in MusicBrainz, or no cover art has been submitted for it
- `405 Method Not Allowed` — unsupported HTTP method used
- `406 Not Acceptable` — cannot generate a response matching the `Accept` header
- `503 Service Unavailable` — rate limit exceeded (theoretical; not currently enforced)

**Note on 307:** The listing endpoint issues a 307 redirect to archive.org. The redirect
target is a URL of the form:
```
https://archive.org/download/mbid-{mbid}/index.json
```
Most HTTP clients follow redirects automatically. The final response is JSON (content-type
is `application/octet-stream` in practice — a known bug, CAA ticket CAA-75 — so clients
should not rely on content-type detection).

**Note on 404:** A 404 means either (a) the MBID does not exist in MusicBrainz, or (b) it
exists but no one has uploaded cover art. There is no way to distinguish these two cases
from the CAA response alone.

---

### 2. `/release/{mbid}/front`

Redirects to the image designated as the front cover for this release.

```
GET https://coverartarchive.org/release/{mbid}/front
```

**Response codes:**
- `307 Temporary Redirect` — front image exists; redirects to binary image on archive.org
- `404 Not Found` — no release with this MBID, or no image has been designated as front

**What "front" means:** The community-curated image most suitable to represent the front
of a release (e.g. for display in a digital music player or store).

---

### 3. `/release/{mbid}/back`

Redirects to the image designated as the back cover.

```
GET https://coverartarchive.org/release/{mbid}/back
```

Same response codes as `/front`. Returns 404 if no image is marked as back.

---

### 4. `/release/{mbid}/{id}`

Fetches a specific image by its numeric ID.

```
GET https://coverartarchive.org/release/{mbid}/{id}
```

`{id}` is the numeric string from the `id` field in the JSON listing (e.g. `361019674`).
Returns a 307 redirect to the full-resolution binary image on archive.org.

---

### 5. `/release/{mbid}/{id}-{size}` and `/release/{mbid}/front-{size}`

Fetches a thumbnail at a specific pixel dimension.

```
GET https://coverartarchive.org/release/{mbid}/front-250
GET https://coverartarchive.org/release/{mbid}/front-500
GET https://coverartarchive.org/release/{mbid}/front-1200
GET https://coverartarchive.org/release/{mbid}/{id}-250
GET https://coverartarchive.org/release/{mbid}/{id}-500
GET https://coverartarchive.org/release/{mbid}/{id}-1200
```

**Valid sizes:** `250`, `500`, `1200` (pixel width)

Returns 307 redirect to thumbnail image. **Important caveat:** The redirect may resolve
to a 404 if the thumbnail has not yet been generated. Thumbnails are created asynchronously
after an image is uploaded. For recently added images, requesting the full-size image
(`/front` without a size suffix) is safer.

---

### 6. `/release-group/{mbid}/`

Returns a JSON listing of cover art for a release group. The images come from the specific
release within the group that has been designated as the "preferred" release for cover art.

```
GET https://coverartarchive.org/release-group/{mbid}/
```

**HTTP methods:** GET, HEAD

**Response codes:**
- `200 OK` — returns JSON directly (unlike the release endpoint, this does NOT return 307)
- `400 Bad Request` — invalid UUID
- `404 Not Found` — no release group with this MBID, or no cover art selected for the group
- `405`, `406`, `503` — same as release endpoint

**Key difference from release endpoint:** Returns 200 directly, not a 307 redirect.

**Extra field:** The response JSON includes a `release` field pointing to the specific
MusicBrainz release URL from which the images were sourced (e.g.
`"http://musicbrainz.org/release/472168df-be3a-44ee-b31d-393155f3366d"`).

---

### 7. `/release-group/{mbid}/front` and `/release-group/{mbid}/front-{size}`

Redirects to the front image for the release group, with optional thumbnail size.

```
GET https://coverartarchive.org/release-group/{mbid}/front
GET https://coverartarchive.org/release-group/{mbid}/front-250
GET https://coverartarchive.org/release-group/{mbid}/front-500
GET https://coverartarchive.org/release-group/{mbid}/front-1200
```

Returns 307 redirect to image. Returns 404 if no front image is designated for the group.

**No `/back` equivalent for release groups.** Only `/front` is defined for the
`release-group` endpoint.

---

### OPTIONS on all endpoints

All endpoints accept HTTP OPTIONS to return the list of allowed methods for that resource.

---

## JSON Response Format

The listing endpoints (`/release/{mbid}/` and `/release-group/{mbid}/`) return a JSON
object. Below is the complete field reference, confirmed from the libcoverart sample JSON
and the official specification.

### Top-level fields

| Field | Type | Description |
|---|---|---|
| `images` | array | List of image objects (see below). May be empty. |
| `release` | string | URL of the MusicBrainz release this art belongs to, e.g. `"http://musicbrainz.org/release/{mbid}"` |

For release-group listings, `release` points to the specific release within the group
that was chosen as the source.

### Image object fields

Each element in the `images` array is an object with these fields:

| Field | Type | Description |
|---|---|---|
| `id` | string | Numeric string; archive.org internal file identifier (e.g. `"361019674"`) |
| `image` | string | Full URL to the original image on coverartarchive.org (not archive.org directly) |
| `thumbnails` | object | URLs for resized versions (see below) |
| `types` | array of strings | One or more image type labels (see Image Types section) |
| `front` | boolean | `true` if this image is the designated front cover |
| `back` | boolean | `true` if this image is the designated back cover |
| `approved` | boolean | `true` if this image has passed MusicBrainz community review |
| `edit` | integer | The MusicBrainz edit ID that added this image |
| `comment` | string | Free-text comment entered by the uploader; often empty string `""` |

### Thumbnails object fields

| Field | Type | Description |
|---|---|---|
| `250` | string | URL for the 250px thumbnail |
| `500` | string | URL for the 500px thumbnail |
| `1200` | string | URL for the 1200px thumbnail |
| `small` | string | Alias for the 250px thumbnail (same URL as `"250"`) |
| `large` | string | Alias for the 500px thumbnail (same URL as `"500"`) |

**Note:** `small`/`large` are legacy aliases. Prefer `"250"` and `"500"` by numeric key.
The `1200` key may not be present in older image records that predate 1200px thumbnail
generation.

### Real example response (from libcoverart sample, trimmed to two images)

```json
{
  "images": [
    {
      "types": ["Front"],
      "front": true,
      "back": false,
      "edit": 16086274,
      "image": "http://coverartarchive.org/release/2592c7ed-1412-4895-b4a6-d9270ddc23fd/361019674.jpg",
      "comment": "",
      "approved": true,
      "thumbnails": {
        "large": "http://coverartarchive.org/release/2592c7ed-1412-4895-b4a6-d9270ddc23fd/361019674-500.jpg",
        "small": "http://coverartarchive.org/release/2592c7ed-1412-4895-b4a6-d9270ddc23fd/361019674-250.jpg"
      },
      "id": "361019674"
    },
    {
      "types": ["Back"],
      "front": false,
      "back": true,
      "edit": 16086289,
      "image": "http://coverartarchive.org/release/2592c7ed-1412-4895-b4a6-d9270ddc23fd/362148876.jpg",
      "comment": "",
      "approved": false,
      "thumbnails": {
        "large": "http://coverartarchive.org/release/2592c7ed-1412-4895-b4a6-d9270ddc23fd/362148876-500.jpg",
        "small": "http://coverartarchive.org/release/2592c7ed-1412-4895-b4a6-d9270ddc23fd/362148876-250.jpg"
      },
      "id": "362148876"
    }
  ],
  "release": "http://musicbrainz.org/release/2592c7ed-1412-4895-b4a6-d9270ddc23fd"
}
```

---

## Image Types

The `types` array on each image object contains zero or more of the following string values.
These are the exact strings that appear in JSON responses.

| Value | What it is |
|---|---|
| `"Front"` | The album front cover — the face of the release packaging, or the art in a digital store |
| `"Back"` | The back of the packaging, usually contains tracklist, barcode, copyright |
| `"Booklet"` | Pages inserted into a jewel case or digipak; may contain lyrics, liner notes, photos |
| `"Medium"` | The disc, vinyl record, or tape itself |
| `"Tray"` | The image behind the tray inside a jewel case (other side of the back inlay) |
| `"Obi"` | The paper strip around the spine of Japanese market releases |
| `"Spine"` | The edge of the packaging visible when stored on a shelf |
| `"Inner"` | Inside of folded packaging (digipak, gatefold vinyl) |
| `"Sleeve"` | The paper/card sleeve surrounding a vinyl or CD |
| `"Box"` | Top surface of box-style packaging |
| `"Panel"` | Individual segment of folded packaging |
| `"Liner"` | Protective sleeve around the medium |
| `"Sticker"` | Adhesive paper attached to the plastic film or packaging |
| `"Poster"` | Poster included with the release |
| `"Track"` | Art associated with a single track (rare) |
| `"Matrix/Runout"` | Scan of the matrix/runout area of a disc (catalogue/pressing data) |
| `"Watermark"` | Image contains added watermarks not part of original artwork |
| `"Raw/Unedited"` | Scan usable for reference but not cleaned up |
| `"Other"` | Anything not covered by the above |

For a DJ library application, only `"Front"` is relevant. Filter `images` for
`image.front == true` or `"Front" in image.types`.

---

## The `cover-art-archive` Field in MusicBrainz Release Responses

This is important for avoiding unnecessary CAA requests. When you fetch a release from
the MusicBrainz API (`/ws/2/release/{mbid}?fmt=json`), the response includes a
`cover-art-archive` subobject:

```json
"cover-art-archive": {
  "artwork": true,
  "count": 13,
  "front": true,
  "back": true,
  "darkened": false
}
```

| Field | Type | Description |
|---|---|---|
| `artwork` | boolean | `true` if any cover art exists for this release |
| `count` | integer | Total number of images uploaded for this release |
| `front` | boolean | `true` if at least one image is designated as front cover |
| `back` | boolean | `true` if at least one image is designated as back cover |
| `darkened` | boolean | `true` if images have been disabled (DMCA or other rights action); art exists but is not publicly accessible |

**This field is only present in individual release lookups.** It is not included in
search results (`/release/?query=...`), only in direct release lookups by MBID.

**Practical use:** Check `cover-art-archive.front == true` before hitting the CAA API.
If false, skip the CAA request entirely. This saves a network round-trip.

**For release groups:** There is no equivalent `cover-art-archive` field in release-group
API responses. You cannot pre-check from the MusicBrainz API whether a release group
has cover art. You must query the CAA directly and handle the 404.

---

## Release vs Release-Group: Which to Use

This is the key practical question for a DJ library application.

### Release lookup (`/release/{mbid}/`)

**Pros:**
- You already have release MBIDs from the MusicBrainz recording lookup
- The MusicBrainz release response includes `cover-art-archive.front` as a pre-check
  flag — no wasted CAA request if false
- The art is specific to the exact pressing/edition you matched

**Cons:**
- A specific pressing may not have art even if other pressings of the same album do
- More variance across releases of the same album

### Release-group lookup (`/release-group/{mbid}/`)

**Pros:**
- The community selects the best-quality front image across all releases in the group
- Higher hit rate: if any release in the group has a good front image, it appears here
- Good for display purposes where you want "the album cover" not "this pressing's cover"

**Cons:**
- No pre-check flag in MusicBrainz API (must hit CAA and accept a potential 404)
- You need the release group MBID, which you get from the AcoustID lookup
  (`releasegroups[].id`) or from the MusicBrainz recording response
  (`releases[].release-group.id` — requires `inc=release-groups`)
- The response includes a `release` field showing which release the art came from,
  but the art itself may not match the specific release you matched

### Recommendation for Crate

Use a two-step fallback:

1. From the MusicBrainz release response, check `cover-art-archive.front`. If true,
   fetch `https://coverartarchive.org/release/{release_mbid}/front-500` and store the
   URL from the 307 redirect target.

2. If the release has no front art (`cover-art-archive.front == false`), and you have
   a release group MBID, try `https://coverartarchive.org/release-group/{rg_mbid}/front-500`.
   Handle 404 gracefully (no art available for this album anywhere in the CAA).

This approach avoids wasted requests for the common case (release has front art) while
falling back to the group-level image when the specific release art is missing.

---

## Error Cases

| HTTP code | Meaning | How to handle |
|---|---|---|
| `200` | Success for release-group listing | Parse JSON |
| `307` | Success (redirect) for release listing and all image endpoints | Follow redirect |
| `400` | Invalid UUID passed | Log error; indicates a bug in the caller |
| `404` | No MBID in MB, or no cover art for this release/group | Store `cover_art_url = NULL`; skip gracefully |
| `405` | Wrong HTTP method (should never happen with GET) | Log error |
| `406` | Bad Accept header | Log error |
| `503` | Rate limit (not currently enforced) | Retry with backoff |

**Key point:** A 404 from the CAA is not an error condition in the application sense. It
means no art is available. Store `NULL` and continue. Do not log as an error.

---

## How Image URLs Work

The `image` field and all thumbnail URLs in the JSON listing are `coverartarchive.org`
URLs, not `archive.org` URLs directly. For example:

```
http://coverartarchive.org/release/2592c7ed-1412-4895-b4a6-d9270ddc23fd/361019674.jpg
```

When fetched, these redirect (307) to the actual archive.org storage URL:

```
https://archive.org/download/mbid-{mbid}/mbid-{mbid}-{id}.jpg
```

The `coverart_redirect` service handles this translation, including resolving MBIDs that
have changed due to MusicBrainz entity merges.

**For Crate:** Store the `coverartarchive.org` URL from the JSON listing, not the final
`archive.org` URL. This means the stored URL remains valid even if archive.org storage
is reorganised, because the redirect layer handles the mapping. Alternatively, if you
only need to display the image at runtime, store only the thumbnail URL pattern
(`/release/{mbid}/front-500`) and resolve it lazily in the frontend.

---

## Image File Naming / ID Generation

The numeric `id` field (e.g. `361019674`) is an archive.org internal identifier. Per the
CAA specification, the ID generation formula is:

```python
id = int((time() - 1327528905) * 100)
```

Where `time()` is Unix time. This is an internal detail; you do not need to generate IDs.
You retrieve them from the JSON listing.

---

## Practical Notes for Electronic Music (Techno/House)

**Coverage expectations:**

The CAA is community-curated. Coverage for electronic music is inconsistent:

- **Major label electronic releases** (Warp, Ninja Tune, XL, !K7): generally good
  coverage, especially for albums.
- **Underground techno/house on small labels** (white labels, promos, limited pressings):
  poor coverage. These releases are often not in MusicBrainz at all, and even those that
  are frequently lack cover art.
- **Digital-only releases** (Bandcamp, Beatport exclusives): variable. Some are well
  documented; many are not.
- **12" singles**: lower coverage than albums overall; many never added to CAA.

No published statistics exist specifically for electronic music. Treat 30-50% miss rate
as a reasonable working assumption for a house/techno DJ library, consistent with the
AcoustID match rate estimate already documented in `research-acoustid.md`.

**Approved flag:**

The `approved` field is `false` for newly added images pending community review. These
images are still accessible and publicly visible — the flag reflects edit workflow state,
not accessibility. Do not filter on `approved`. In practice, unapproved images display
the same as approved ones.

**No 1200px key in older records:**

Images uploaded before 1200px thumbnails were introduced will have only `small`/`large`
(250px/500px) in their `thumbnails` object. Always check for key existence before using
`thumbnails["1200"]`.

**HTTP vs HTTPS in stored URLs:**

The sample JSON and some API responses still use `http://coverartarchive.org/...` URLs
(no TLS). The service supports HTTPS. When storing or displaying URLs, upgrade `http://`
to `https://` or request via HTTPS from the start.

---

## python-musicbrainzngs Integration

The `musicbrainzngs` library (already in use for MusicBrainz lookups) includes a
`musicbrainzngs.caa` module. However, all its functions download the full binary image
data, which is not what Crate needs at this stage.

For Crate, make direct HTTP requests to get the listing JSON and extract the URL. Do not
use `get_image_front()` etc. from musicbrainzngs — those download bytes.

Useful functions from `musicbrainzngs.caa` if you want to use them later:

```python
# Get the full listing (returns parsed JSON as dict)
musicbrainzngs.get_image_list(release_mbid)

# Get release group listing (returns parsed JSON as dict)
musicbrainzngs.get_release_group_image_list(release_group_mbid)
```

These return the dict equivalent of the JSON documented above. For URL extraction only,
it is simpler to call the CAA HTTP API directly and read the `images[0]` URL without
downloading image bytes.

---

## Minimal Implementation Pattern for Crate

The pattern below stores only the URL, following the recommendation in this document.

```python
import requests

CAA_BASE = "https://coverartarchive.org"

def get_front_cover_url(release_mbid: str, size: int = 500) -> str | None:
    """
    Return the cover art URL for a release, or None if unavailable.
    Uses the /front endpoint and captures the redirect target URL
    without downloading the image.
    size: 250, 500, or 1200
    """
    url = f"{CAA_BASE}/release/{release_mbid}/front-{size}"
    try:
        resp = requests.get(url, allow_redirects=False, timeout=5)
        if resp.status_code == 307:
            return resp.headers.get("Location")
        # 404 = no art; treat as normal, return None
        return None
    except requests.RequestException:
        return None


def get_front_cover_url_with_fallback(
    release_mbid: str,
    release_group_mbid: str | None,
    size: int = 500,
) -> str | None:
    """Try release first, then release group."""
    url = get_front_cover_url(release_mbid, size)
    if url:
        return url
    if release_group_mbid:
        rg_url = f"{CAA_BASE}/release-group/{release_group_mbid}/front-{size}"
        try:
            resp = requests.get(rg_url, allow_redirects=False, timeout=5)
            if resp.status_code == 307:
                return resp.headers.get("Location")
        except requests.RequestException:
            pass
    return None
```

Note: `allow_redirects=False` is used to capture the redirect URL without downloading
the image binary.

---

## Summary of Key Facts

| Question | Answer |
|---|---|
| Base URL | `https://coverartarchive.org` |
| Auth required | No |
| Rate limit | None currently enforced (503 defined but inactive) |
| Release listing | GET `/release/{mbid}/` → 307 redirect to JSON |
| Release group listing | GET `/release-group/{mbid}/` → 200 JSON directly |
| Front image URL | GET `/release/{mbid}/front` → 307 to binary image |
| Thumbnail sizes | 250, 500, 1200 (px width) |
| No art response | 404 |
| JSON top-level fields | `images[]`, `release` |
| Image fields | `id`, `image`, `thumbnails`, `types`, `front`, `back`, `approved`, `edit`, `comment` |
| Thumbnail keys | `"250"`, `"500"`, `"1200"`, `"small"` (=250), `"large"` (=500) |
| Pre-check for art | `cover-art-archive.front` in MB release response (release only, not group) |
| `darkened` flag | Images exist but are rights-disabled; treat same as no art |
| Best strategy for Crate | Check MB release `cover-art-archive.front`; hit CAA only if true; fall back to release-group |
