# Potential Features

The following are ideas for future improvements:

### Data & Coverage
- **Stall deduplication** — automatically detect and merge duplicate stall entries caused by spelling variations or multiple location tags
- **Opening hours** — enrich stall data with operating hours sourced from posts or external APIs
- **Stall closure tracking** — detect posts announcing temporary or permanent closures and surface this on the map
- **Historical trend view** — show how post frequency and sentiment for a stall changes over time

### Map & UI
- **Stall profile pages** — dedicated pages per stall with a full photo gallery, all posts, and rating history
- **Filter by image type** — let users filter the map to show only stalls with noodle photos
- **Filter by rating / recency** — additional sidebar filters beyond current sort options
- **Mobile-optimised lightbox** — pinch-to-zoom and swipe navigation improvements on touch devices
- **Contributor leaderboard** — highlight the most active posters in the group

### Intelligence
- **Price extraction** — parse dollar amounts from post text to show average price per stall
- **Queue / wait time signals** — detect mentions of queue length or wait time from posts
- **Dish variant tagging** — distinguish wet vs dry Hokkien mee from post text or image classification
- **Auto-suggest location corrections** — flag posts where the geocoded location looks suspicious and suggest alternatives

### Infrastructure
- **Scheduled refresh** — automated daily/weekly re-scrape and map rebuild via GitHub Actions
- **Admin dashboard** — a simple UI for reviewing and applying location overrides without editing JSON manually
- **Image CDN / caching** — serve images from a CDN to reduce load times and broken image fallbacks
