"""
Extract posts, comments, and image URLs from a public Facebook group
using Playwright (headless browser).

Usage:
    python extractor/extract_group.py [--pages PAGES] [--cookies COOKIES] [--debug]

Output:
    output/group_posts.json
"""

import argparse
from datetime import datetime, timezone
import json
import os
import random
import sys
import time

from playwright.sync_api import sync_playwright

# Hokkien Mee Hunting
# https://www.facebook.com/groups/227074250721100/
GROUP_ID = "227074250721100"
GROUP_URL = f"https://www.facebook.com/groups/{GROUP_ID}/?sorting_setting=CHRONOLOGICAL"
DEFAULT_COOKIES = "facebook_cookies.txt"
OUTPUT_DIR = "output"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "group_posts.json")

# How many times to scroll down per "page"
SCROLLS_PER_PAGE = 3
SCROLL_PAUSE_MIN = 3  # min seconds between scrolls
SCROLL_PAUSE_MAX = 6  # max seconds between scrolls


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract posts from a Facebook group using Playwright."
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=5,
        help="Number of scroll batches (default: 5). Use 0 for unlimited.",
    )
    parser.add_argument(
        "--cookies",
        type=str,
        default=DEFAULT_COOKIES,
        help=f"Path to Netscape cookies.txt file (default: {DEFAULT_COOKIES}).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Run browser in headed (visible) mode for debugging.",
    )
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Keep scrolling even when no new posts are found (for fetching older posts past already-extracted ones).",
    )
    return parser.parse_args()


def parse_netscape_cookies(cookies_file):
    """Parse a Netscape cookies.txt file into a list of cookie dicts for Playwright."""
    cookies = []
    with open(cookies_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue

            domain, _, path, secure, expires, name, value = parts[:7]

            cookie = {
                "name": name,
                "value": value,
                "domain": domain,
                "path": path,
                "secure": secure.upper() == "TRUE",
                "httpOnly": False,
            }

            # Only set expires if it's a valid positive timestamp
            try:
                exp = int(expires)
                if exp > 0:
                    cookie["expires"] = exp
            except ValueError:
                pass

            cookies.append(cookie)

    return cookies


def scroll_page(page, times, pause_min, pause_max, debug=False):
    """Scroll down the page with randomised delays to avoid rate limiting."""
    initial_height = page.evaluate("document.body.scrollHeight")
    if debug:
        print(f"    Initial page height: {initial_height}px")
    
    for i in range(times):
        # Scroll by a random portion of the viewport to look more human
        scroll_amount = random.randint(600, 1200)
        page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        
        # Wait a bit for the initial scroll
        time.sleep(random.uniform(1, 2))
        
        # Check if we're near the bottom and wait for Facebook to load more content
        distance_from_bottom = page.evaluate("""
        () => {
            const scrollPos = window.pageYOffset;
            const windowHeight = window.innerHeight;
            const docHeight = document.documentElement.scrollHeight;
            return docHeight - (scrollPos + windowHeight);
        }
        """)
        
        if debug:
            current_scroll = page.evaluate("window.pageYOffset")
            page_height = page.evaluate("document.body.scrollHeight")
            print(f"    Scroll {i+1}/{times}: scrolled {scroll_amount}px, now at {current_scroll}px, page height {page_height}px, distance from bottom: {distance_from_bottom}px")
        
        # If we're close to the bottom, wait longer for Facebook to load more content
        if distance_from_bottom < 2000:  # Within 2000px of bottom
            if debug:
                print(f"    Near bottom, waiting for Facebook to load more content...")
            
            # Wait for loading indicators to appear and disappear
            max_wait_time = 15  # seconds
            wait_start = time.time()
            
            while time.time() - wait_start < max_wait_time:
                # Check for loading indicators
                has_loading = page.evaluate("""
                () => {
                    const loadingEls = document.querySelectorAll(
                        '[role="progressbar"], [aria-label*="Loading"], [aria-label*="loading"], ' +
                        '.loading, [data-testid*="loading"], [aria-busy="true"]'
                    );
                    return loadingEls.length > 0;
                }
                """)
                
                if has_loading:
                    if debug:
                        print(f"    Loading indicator found, waiting...")
                    time.sleep(2)
                else:
                    # No loading indicator, wait a bit more then check if height changed
                    time.sleep(1)
                    new_height = page.evaluate("document.body.scrollHeight")
                    if new_height > page_height:
                        if debug:
                            print(f"    Page height increased to {new_height}px, content loaded")
                        break
                    elif time.time() - wait_start > 5:  # Waited at least 5 seconds without loading
                        if debug:
                            print(f"    No new content loaded after {time.time() - wait_start:.1f}s")
                        break
        
        # Regular pause between scrolls
        pause = random.uniform(pause_min, pause_max)
        time.sleep(pause)
    
    final_height = page.evaluate("document.body.scrollHeight")
    height_change = final_height - initial_height
    if debug:
        print(f"    Page height changed by {height_change}px (was {initial_height}, now {final_height})")
    
    return height_change > 0


def _is_on_feed(page):
    """Check if we're on the group feed page (not an individual post page)."""
    url = page.url
    # A post page contains /posts/, /permalink/, or story_fbid in the URL
    if '/posts/' in url or '/permalink/' in url or 'story_fbid' in url:
        return False
    # Should be on the group page
    return '/groups/' + GROUP_ID in url


def _dismiss_dialog(page):
    """Close any Facebook dialog/modal overlay. Returns True if one was found and dismissed."""
    try:
        dialog = page.locator('[role="dialog"]')
        if dialog.count() > 0:
            # Try the close button inside the dialog
            close_btn = dialog.first.locator(
                '[aria-label="Close"], [aria-label="close"]'
            )
            if close_btn.count() > 0:
                close_btn.first.click(timeout=2000)
                time.sleep(1)
                # Check if dialog is gone
                if page.locator('[role="dialog"]').count() == 0:
                    return True
            # Try Escape key
            page.keyboard.press("Escape")
            time.sleep(1)
            if page.locator('[role="dialog"]').count() == 0:
                return True
            # Try Escape again (sometimes Facebook needs it twice)
            page.keyboard.press("Escape")
            time.sleep(1)
            return True
    except Exception:
        pass
    return False


def _return_to_feed(page, debug=False):
    """Navigate back to the group feed if we've left it."""
    try:
        if _is_on_feed(page):
            # Still on feed URL but might have a dialog overlay
            _dismiss_dialog(page)
            return True

        if debug:
            print(f"  Debug: Not on feed (current URL: {page.url[:100]}...)")

        # First try: close any dialog/modal overlay
        if _dismiss_dialog(page):
            if _is_on_feed(page):
                if debug:
                    print("  Debug: Returned to feed after dismissing dialog")
                return True

        # Second try: go back
        try:
            if debug:
                print("  Debug: Trying to go back...")
            page.go_back(wait_until="domcontentloaded", timeout=10000)
            time.sleep(2)
            if _is_on_feed(page):
                if debug:
                    print("  Debug: Successfully went back to feed")
                return True
        except Exception as e:
            if debug:
                print(f"  Debug: Go back failed: {e}")
            pass

        # Last resort: navigate directly to the group URL
        try:
            if debug:
                print(f"  Debug: Navigating directly to {GROUP_URL}...")
            page.goto(GROUP_URL, wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)
            if debug:
                print("  Debug: Successfully navigated to group URL")
            return True
        except Exception as e:
            if debug:
                print(f"  Debug: Direct navigation failed: {e}")
            return False
    except Exception as e:
        if debug:
            print(f"  Debug: _return_to_feed caught exception: {e}")
        return False


def click_see_more(page):
    """Click all 'See more' links on currently loaded posts to expand truncated text."""
    if not _is_on_feed(page):
        return 0
    try:
        # Facebook uses several patterns for "See more" buttons
        see_more_links = page.locator(
            'div[role="button"]:has-text("See more"), '
            'span[role="button"]:has-text("See more")'
        )
        count = see_more_links.count()
        clicked = 0
        for i in range(count):
            try:
                link = see_more_links.nth(i)
                text = link.inner_text(timeout=1000)
                if text.strip().lower() == "see more":
                    link.scroll_into_view_if_needed(timeout=2000)
                    link.click(timeout=2000)
                    clicked += 1
                    time.sleep(0.5)
                    # Always check for and dismiss any dialog that opened
                    if _dismiss_dialog(page):
                        print("  Dismissed dialog after 'See more' click")
                    # If we left the feed, return immediately
                    if not _is_on_feed(page):
                        print("  Warning: 'See more' click navigated away, returning to feed...")
                        _return_to_feed(page)
                        return clicked
            except Exception:
                pass
        if clicked > 0:
            time.sleep(1)
        return clicked
    except Exception:
        return 0


def extract_comments_for_post(context, post, debug=False):
    """Open a post's individual page in a new tab to extract all comments.

    Facebook only shows 1-2 comments inline on the feed. To get all comments,
    we navigate to the individual post page where all comments are accessible.
    Uses a separate tab so the main feed page keeps its scroll position.
    """
    post_link = post.get('post_link', '')
    if not post_link:
        return

    tab = context.new_page()
    try:
        tab.goto(post_link, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)

        # Expand all comment sections (View more comments, replies, etc.)
        total_expanded = 0
        for _round in range(15):
            clicked_this_round = 0
            patterns = [
                'div[role="button"]:has-text("View more comments")',
                'div[role="button"]:has-text("View previous comments")',
                'div[role="button"]:has-text("View all")',
                'div[role="button"]:has-text("View 1 reply")',
                'div[role="button"]:has-text("View 1 more reply")',
                'div[role="button"]:has-text("replies")',
                'span[role="button"]:has-text("View more comments")',
                'span[role="button"]:has-text("View previous comments")',
                'span[role="button"]:has-text("replies")',
            ]
            for pattern in patterns:
                try:
                    links = tab.locator(pattern)
                    count = links.count()
                    for i in range(count):
                        if total_expanded >= 100:
                            break
                        try:
                            link = links.nth(i)
                            text = link.inner_text(timeout=1000).strip().lower()
                            if any(kw in text for kw in [
                                'view more comment', 'view previous',
                                'view all', 'view 1 reply', 'view 1 more',
                                'more replies', 'replies',
                            ]):
                                link.scroll_into_view_if_needed(timeout=2000)
                                link.click(timeout=2000)
                                clicked_this_round += 1
                                total_expanded += 1
                                time.sleep(1)
                        except Exception:
                            pass
                except Exception:
                    pass
            if clicked_this_round == 0:
                break
            time.sleep(1)

        # Expand "See more" links inside comments
        try:
            see_more = tab.locator('div[role="button"]')
            count = see_more.count()
            for i in range(count):
                try:
                    link = see_more.nth(i)
                    t = link.inner_text(timeout=500).strip()
                    if t.lower() == 'see more':
                        link.scroll_into_view_if_needed(timeout=2000)
                        link.click(timeout=2000)
                        time.sleep(0.5)
                except Exception:
                    pass
        except Exception:
            pass

        # Extract all comments from the post page
        comments = tab.evaluate("""
        () => {
            const comments = [];
            const commentArticles = document.querySelectorAll('[role="article"]');

            for (const ca of commentArticles) {
                const cLabel = ca.getAttribute('aria-label') || '';
                if (!cLabel.startsWith('Comment by ')) continue;

                let cAuthor = '';
                let cTimestamp = '';
                let cAuthorLink = '';

                const rest = cLabel.substring('Comment by '.length);
                const tsPatterns = [
                    /(.*?)\\s+(about\\s+(?:an?|\\d+)\\s+\\w+\\s+ago)$/i,
                    /(.*?)\\s+((?:a|an|\\d+)\\s+\\w+\\s+ago)$/i,
                    /(.*?)\\s+(just now)$/i,
                    /(.*?)\\s+(yesterday)$/i,
                    /(.*?)\\s+(\\d+[hdwmy])$/i,
                ];
                for (const pat of tsPatterns) {
                    const m = rest.match(pat);
                    if (m) {
                        cAuthor = m[1].trim();
                        cTimestamp = m[2].trim();
                        break;
                    }
                }
                if (!cAuthor && rest) {
                    cAuthor = rest.trim();
                }

                const cUserLink = ca.querySelector('a[href*="/user/"], a[href*="/profile.php"]');
                if (cUserLink) {
                    cAuthorLink = cUserLink.href.split('?')[0];
                    if (!cAuthor) {
                        let linkText = cUserLink.innerText.trim();
                        if (!linkText || linkText === 'Facebook') {
                            const nameSpan = cUserLink.querySelector('span');
                            if (nameSpan) linkText = nameSpan.innerText.trim();
                        }
                        if (linkText && linkText !== 'Facebook') cAuthor = linkText;
                    }
                }

                if (!cAuthor && cAuthorLink) {
                    const allAnchors = ca.querySelectorAll('a');
                    for (const a of allAnchors) {
                        if (a.href && a.href.split('?')[0] === cAuthorLink) {
                            const t = a.innerText.trim();
                            if (t && t.length > 1 && t !== 'Facebook') {
                                cAuthor = t;
                                break;
                            }
                        }
                    }
                }

                const cTextEls = ca.querySelectorAll('[dir="auto"]');
                const cSeen = new Set();
                const cParts = [];
                const cSkipLower = new Set([
                    cAuthor.toLowerCase(), 'like', 'reply', 'share',
                    'top contributor', 'follow', 'following',
                    'all-star contributor', 'new member',
                    'rising star', 'group expert', 'moderator', 'admin',
                ]);

                for (const el of cTextEls) {
                    const t = el.innerText.trim();
                    if (!t || t.length <= 1) continue;
                    if (cSkipLower.has(t.toLowerCase())) continue;
                    if (cSeen.has(t)) continue;
                    cSeen.add(t);
                    cParts.push(t);
                }
                const cText = cParts.join(' ');

                const cImages = [];
                const cImgs = ca.querySelectorAll('img');
                for (const img of cImgs) {
                    const src = img.src || '';
                    if (src.includes('scontent') && !src.includes('rsrc.php')) {
                        cImages.push(src);
                    }
                }

                if (cAuthor || cText) {
                    comments.push({
                        author: cAuthor,
                        author_link: cAuthorLink,
                        text: cText,
                        images: cImages,
                        timestamp: cTimestamp,
                    });
                }
            }
            return comments;
        }
        """)

        if comments:
            post['comments'] = comments
        if debug:
            print(f"    Post {post.get('post_id', '?')}: {len(comments)} comments")
    except Exception as e:
        if debug:
            print(f"    Error extracting comments for {post.get('post_id', '?')}: {e}")
    finally:
        tab.close()


def extract_posts_from_page(page, debug=False):
    """Extract post data from the currently loaded page using JS evaluation.

    Facebook's DOM structure:
    - [role="feed"] is the main feed container
    - Direct children of the feed are post containers (NOT role="article")
    - Comments inside posts use role="article" with aria-label="Comment by ..."
    - Post text, images, etc. live outside of comment articles
    """

    # Detect the logged-in user's display name so we can skip it
    # Facebook shows "Write a comment…" placeholder near a profile image
    # whose aria-label contains the user's name, or in the nav bar.
    logged_in_user = page.evaluate("""
    () => {
        // Try the profile photo in the comment box
        const commentImg = document.querySelector('form[role="presentation"] image, form img[alt]');
        if (commentImg) {
            const alt = commentImg.getAttribute('alt') || '';
            if (alt && alt !== 'Facebook') return alt.split(',')[0].trim();
        }
        // Try navigation bar profile link
        const navLink = document.querySelector('[role="navigation"] a[aria-label]');
        if (navLink) {
            const label = navLink.getAttribute('aria-label') || '';
            if (label && !['Facebook', 'Home', 'Watch'].includes(label)) return label.trim();
        }
        return '';
    }
    """) or ""

    if debug and logged_in_user:
        print(f"  Detected logged-in user: {logged_in_user}")

    posts = page.evaluate("""
    (loggedInUser) => {
        const results = [];
        const loggedInLower = (loggedInUser || '').toLowerCase();
        const loggedInFirst = loggedInLower.split(' ')[0];

        // The feed container holds all posts as direct children
        const feed = document.querySelector('[role="feed"]');
        if (!feed) return results;

        const feedChildren = [...feed.children];

        for (const container of feedChildren) {
            try {
                // A real post must have a post link
                const postLinkEl = container.querySelector(
                    'a[href*="/posts/"], a[href*="/permalink/"], a[href*="story_fbid"]'
                );
                if (!postLinkEl) continue;

                const postLink = postLinkEl.href.split('?')[0];
                let postId = '';
                const idMatch = postLink.match(/posts\\/(\\d+)/) ||
                                postLink.match(/permalink\\/(\\d+)/) ||
                                postLink.match(/story_fbid=(\\d+)/);
                if (idMatch) postId = idMatch[1];

                // --- Identify comment articles so we can exclude them ---
                const commentArticles = container.querySelectorAll('[role="article"]');
                const commentEls = new Set();
                commentArticles.forEach(ca => commentEls.add(ca));

                // Build a set of all elements that belong to comments
                const insideComment = (el) => {
                    let node = el;
                    while (node && node !== container) {
                        if (commentEls.has(node)) return true;
                        node = node.parentElement;
                    }
                    return false;
                };

                // --- Author & header context ---
                // The h2/h3 contains the author name plus optional context,
                // e.g. "Darren Chow is at Chuan Fried Hokkien Prawn Mee 川炒福建虾面."
                let author = '';
                let authorLink = '';
                let headerContext = '';
                const header = container.querySelector('h2, h3');
                if (header) {
                    const fullHeaderText = header.innerText.trim();
                    const headerAnchor = header.querySelector('a');
                    if (headerAnchor) {
                        author = headerAnchor.innerText.trim();
                        // Everything after the author name is context (check-in, shared, etc.)
                        if (fullHeaderText.length > author.length) {
                            headerContext = fullHeaderText.substring(author.length).trim();
                        }
                    } else {
                        author = fullHeaderText;
                    }
                }
                // Author profile link
                const userLink = container.querySelector('a[href*="/user/"], a[href*="/profile.php"]');
                if (userLink) {
                    authorLink = userLink.href.split('?')[0];
                    if (!author) {
                        const linkText = userLink.innerText.trim();
                        if (linkText && linkText !== 'Facebook') author = linkText;
                    }
                }

                // --- Timestamp ---
                // Facebook shows relative time as the text of a link to the post
                let timestamp = '';
                const allLinks = container.querySelectorAll('a');
                for (const link of allLinks) {
                    const href = link.href || '';
                    if (!(href.includes('/posts/') || href.includes('/permalink/'))) continue;
                    const lt = link.innerText.trim();
                    // Match patterns like "4d", "6h", "2w", "1y", "3 hrs", "Just now"
                    if (lt && lt.length < 30 && lt.length > 0 &&
                        /^(\\d+[hdwmy]|\\d+\\s*(hr|hour|min|day|week|month|year)s?|just now|yesterday)/i.test(lt)) {
                        timestamp = lt;
                        break;
                    }
                }

                // --- Post text (outside of comments) ---
                const textBlocks = container.querySelectorAll('[dir="auto"]');
                const seen = new Set();
                const textParts = [];
                // Known UI strings and author variations to skip
                const skipLower = new Set([
                    'facebook',
                    'like', 'reply', 'share', 'send', 'comment',
                    'top contributor', 'all-star contributor',
                    'new member', 'rising star', 'group expert',
                    'moderator', 'admin', 'follow', 'following',
                    'most relevant', 'all comments', 'newest',
                    'write a comment…', 'write a comment',
                    'suggested for you', 'see original',
                ]);

                for (const block of textBlocks) {
                    // Skip text inside comment articles
                    if (insideComment(block)) continue;

                    const t = block.innerText.trim();
                    if (!t || t.length <= 1) continue;

                    const tLower = t.toLowerCase();
                    if (skipLower.has(tLower)) continue;

                    // Skip author name, badge text
                    if (tLower === author.toLowerCase()) continue;

                    // Skip logged-in user's display name (appears in "comment as" area)
                    if (loggedInFirst && (tLower === loggedInLower || tLower === loggedInFirst)) continue;

                    // Skip UI patterns
                    if (/^\\d+\\s*comments?$/i.test(t)) continue;
                    if (/^\\d+\\s*shares?$/i.test(t)) continue;
                    if (/^Photos? from /i.test(t)) continue;
                    if (/^\\d+[hdwmy]$/i.test(t)) continue;
                    if (/^View\\s+(more\\s+comments|all\\s+\\d+|\\d+)\\s*(replies|reply|comments?)?/i.test(t)) continue;

                    // Skip obfuscated/anti-scraping junk:
                    // - Random-looking .com domains (e.g. "R73TRNF.com", "PlKH1M3ZN.com")
                    if (/^[A-Za-z0-9]{4,15}\\.(com|net|org|me)$/i.test(t)) continue;
                    // - "m.me" and similar very short URLs
                    if (/^[a-z]{1,3}\\.[a-z]{2,4}$/i.test(t)) continue;
                    // - Long scrambled strings (mix of letters/numbers/spaces, no real words)
                    if (t.length > 25 && /^[a-zA-Z0-9\\s]{25,}$/.test(t) &&
                        !/\\s[a-z]{3,}\\s/i.test(t)) continue;
                    // - Very long random-looking strings without spaces
                    if (t.length > 20 && /^[a-zA-Z0-9]{20,}$/.test(t)) continue;
                    // - Strings that are mostly single chars on separate lines (anti-scraping)
                    const lines = t.split('\\n');
                    if (lines.length > 5 && lines.filter(l => l.trim().length <= 2).length > lines.length * 0.6) continue;

                    // Skip if it's a duplicate
                    if (seen.has(t)) continue;

                    // Skip if this text is a substring of something we already have
                    let isSubstring = false;
                    for (const existing of seen) {
                        if (existing.includes(t)) { isSubstring = true; break; }
                    }
                    if (isSubstring) continue;

                    // If this text contains a previous entry, remove the shorter one
                    const toRemove = [];
                    for (const existing of seen) {
                        if (t.includes(existing)) toRemove.push(existing);
                    }
                    for (const r of toRemove) {
                        seen.delete(r);
                        const idx = textParts.indexOf(r);
                        if (idx !== -1) textParts.splice(idx, 1);
                    }

                    seen.add(t);
                    textParts.push(t);
                }

                // Join all remaining text parts and clean up
                let text = textParts.join('\\n');
                // Strip trailing "See more" / "… See more" that wasn't expanded
                text = text.replace(/\\s*…?\\s*See more\\s*$/i, '').trim();

                // --- Location (from header context like "is at <Place>") ---
                let location = '';
                if (headerContext) {
                    // Match "is at <Place>" or "at <Place>" patterns
                    const atMatch = headerContext.match(/(?:is\\s+)?at\\s+(.+)/i);
                    if (atMatch) {
                        location = atMatch[1].replace(/\\.$/, '').trim();
                    }
                }

                // --- Images (outside of comments) ---
                const images = [];
                const allImgs = container.querySelectorAll('img');
                const seenImgSrc = new Set();
                for (const img of allImgs) {
                    if (insideComment(img)) continue;
                    const src = img.src || '';
                    if (!src.includes('scontent')) continue;
                    if (src.includes('rsrc.php')) continue;
                    // Normalise by removing query params for dedup
                    const base = src.split('?')[0];
                    if (seenImgSrc.has(base)) continue;
                    seenImgSrc.add(base);
                    images.push(src);
                }

                // --- Reactions ---
                let reactions = '';
                const reactEl = container.querySelector(
                    '[aria-label*="reaction"], [aria-label*="people reacted"]'
                );
                if (reactEl) {
                    reactions = reactEl.getAttribute('aria-label') || '';
                }

                // --- Comments ---
                const comments = [];
                for (const ca of commentArticles) {
                    const cLabel = ca.getAttribute('aria-label') || '';
                    let cAuthor = '';
                    let cTimestamp = '';
                    let cAuthorLink = '';

                    // Parse "Comment by <name> <time>" from aria-label.
                    // The timestamp is always at the end; use a greedy match
                    // for the name so multi-word names work correctly.
                    // Patterns: "47 minutes ago", "about an hour ago", "2 days ago",
                    //           "just now", "yesterday", "4d", "6h"
                    if (cLabel.startsWith('Comment by ')) {
                        const rest = cLabel.substring('Comment by '.length);
                        // Try to match a known timestamp suffix
                        const tsPatterns = [
                            /(.*?)\\s+(about\\s+(?:an?|\\d+)\\s+\\w+\\s+ago)$/i,
                            /(.*?)\\s+((?:a|an|\\d+)\\s+\\w+\\s+ago)$/i,
                            /(.*?)\\s+(just now)$/i,
                            /(.*?)\\s+(yesterday)$/i,
                            /(.*?)\\s+(\\d+[hdwmy])$/i,
                        ];
                        for (const pat of tsPatterns) {
                            const m = rest.match(pat);
                            if (m) {
                                cAuthor = m[1].trim();
                                cTimestamp = m[2].trim();
                                break;
                            }
                        }
                        // If no timestamp matched, take the whole thing as author
                        if (!cAuthor && rest) {
                            cAuthor = rest.trim();
                        }
                    }

                    // Commenter profile link
                    const cUserLink = ca.querySelector('a[href*="/user/"], a[href*="/profile.php"]');
                    if (cUserLink) {
                        cAuthorLink = cUserLink.href.split('?')[0];
                        if (!cAuthor) {
                            // Try the link text first
                            let linkText = cUserLink.innerText.trim();
                            // Facebook sometimes nests the name in a child span
                            if (!linkText || linkText === 'Facebook') {
                                const nameSpan = cUserLink.querySelector('span');
                                if (nameSpan) linkText = nameSpan.innerText.trim();
                            }
                            if (linkText && linkText !== 'Facebook') cAuthor = linkText;
                        }
                    }

                    // Last-resort fallback: extract author from the user URL path
                    if (!cAuthor && cAuthorLink) {
                        // Try to find any <a> in the comment whose href matches
                        // the author link and has visible text
                        const allAnchors = ca.querySelectorAll('a');
                        for (const a of allAnchors) {
                            if (a.href && a.href.split('?')[0] === cAuthorLink) {
                                const t = a.innerText.trim();
                                if (t && t.length > 1 && t !== 'Facebook') {
                                    cAuthor = t;
                                    break;
                                }
                            }
                        }
                    }

                    // Comment text
                    const cTextEls = ca.querySelectorAll('[dir="auto"]');
                    const cSeen = new Set();
                    const cParts = [];
                    const cSkipLower = new Set([
                        cAuthor.toLowerCase(), 'like', 'reply', 'share',
                        'top contributor', 'follow', 'following',
                        'all-star contributor', 'new member',
                        'rising star', 'group expert', 'moderator', 'admin',
                    ]);

                    for (const el of cTextEls) {
                        const t = el.innerText.trim();
                        if (!t || t.length <= 1) continue;
                        if (cSkipLower.has(t.toLowerCase())) continue;
                        if (cSeen.has(t)) continue;
                        cSeen.add(t);
                        cParts.push(t);
                    }
                    const cText = cParts.join(' ');

                    // Comment images
                    const cImages = [];
                    const cImgs = ca.querySelectorAll('img');
                    for (const img of cImgs) {
                        const src = img.src || '';
                        if (src.includes('scontent') && !src.includes('rsrc.php')) {
                            cImages.push(src);
                        }
                    }

                    if (cAuthor || cText) {
                        comments.push({
                            author: cAuthor,
                            author_link: cAuthorLink,
                            text: cText,
                            images: cImages,
                            timestamp: cTimestamp,
                        });
                    }
                }

                if (text || images.length > 0 || postId) {
                    results.push({
                        post_id: postId,
                        author: author,
                        author_link: authorLink,
                        timestamp: timestamp,
                        extracted_at: new Date().toISOString(),
                        text: text,
                        location: location,
                        images: images,
                        reactions: reactions,
                        comments: comments,
                        post_link: postLink,
                    });
                }
            } catch (e) {
                // Skip posts that fail to parse
            }
        }
        return results;
    }
    """, logged_in_user)

    if debug and posts:
        print(f"\n--- DEBUG: Sample post ---")
        sample = posts[0]
        for key, val in sample.items():
            if key == 'text':
                print(f"  {key}: {repr(val[:200])}")
            elif key == 'images':
                print(f"  {key}: {len(val)} images")
            elif key == 'comments':
                print(f"  {key}: {len(val)} comments")
                for c in val[:2]:
                    print(f"    - {c.get('author')}: {c.get('text', '')[:80]}")
            else:
                print(f"  {key}: {val}")
        print("---\n")
        
        # Debug: Check for duplicate post IDs in this batch
        post_ids = [p.get('post_id') for p in posts if p.get('post_id')]
        if len(post_ids) != len(set(post_ids)):
            print(f"  WARNING: Found duplicate post IDs in this batch: {post_ids}")

    return posts


def deduplicate_posts(posts):
    """Remove duplicate posts based on post_id or text content."""
    seen = set()
    unique = []
    for post in posts:
        key = post.get("post_id") or post.get("text", "")[:100]
        if key and key not in seen:
            seen.add(key)
            unique.append(post)
    return unique


def main():
    args = parse_args()

    if not os.path.exists(args.cookies):
        print(f"Error: Cookies file not found at '{args.cookies}'.")
        print("See README.md for instructions on how to export your Facebook cookies.")
        sys.exit(1)

    cookie_size = os.path.getsize(args.cookies)
    if cookie_size == 0:
        print("Error: Cookies file is empty. Re-export your cookies.")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Cookies file: {args.cookies} ({cookie_size} bytes)")
    print(f"Group URL: {GROUP_URL}")
    print(f"Scroll batches: {args.pages if args.pages else 'unlimited'}")
    mode_parts = []
    if args.debug:
        mode_parts.append("headed (debug)")
    else:
        mode_parts.append("headless")
    if args.backfill:
        mode_parts.append("backfill")
    print(f"Mode: {', '.join(mode_parts)}\n")

    cookies = parse_netscape_cookies(args.cookies)
    print(f"Parsed {len(cookies)} cookies from file")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.debug)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        # Load cookies
        context.add_cookies(cookies)
        page = context.new_page()

        print(f"Navigating to {GROUP_URL} ...")
        page.goto(GROUP_URL, wait_until="domcontentloaded", timeout=60000)
        # Give Facebook time to render posts via JS
        time.sleep(5)

        # Handle potential login redirect or cookie consent
        if "login" in page.url.lower():
            print("\nError: Redirected to login page. Your cookies may have expired.")
            print("Re-export cookies from your browser and try again.")
            browser.close()
            sys.exit(1)

        # Close any popups (e.g., "Not now" for notifications)
        try:
            page.click('div[aria-label="Close"]', timeout=3000)
        except Exception:
            pass

        print("Page loaded. Starting extraction...\n")
        print("Sort order: chronological (via URL parameter)")

        # Load existing posts if output file exists (append/update mode)
        all_posts = []
        posts_by_id = {}  # key -> index in all_posts for in-place updates
        if os.path.exists(OUTPUT_FILE):
            try:
                with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Support both envelope format and legacy flat array
                if isinstance(data, dict) and "posts" in data:
                    all_posts = data["posts"]
                elif isinstance(data, list):
                    all_posts = data
                for idx, p in enumerate(all_posts):
                    key = p.get("post_id") or p.get("text", "")[:100]
                    if key:
                        posts_by_id[key] = idx
                print(f"Loaded {len(all_posts)} existing posts from {OUTPUT_FILE} (append/update mode)\n")
            except (json.JSONDecodeError, IOError):
                print(f"Warning: Could not read {OUTPUT_FILE}, starting fresh.\n")

        batch = 0
        consecutive_empty = 0
        max_batches = args.pages if args.pages > 0 else 999999

        while batch < max_batches:
            batch += 1
            print(f"Scroll batch {batch}/{args.pages if args.pages else '∞'}...")

            # Check current scroll position before scrolling
            scroll_before = page.evaluate("window.pageYOffset")
            height_before = page.evaluate("document.body.scrollHeight")
            
            # If we got very few posts in previous batches, try scrolling more aggressively
            if batch > 1 and len(posts) <= 3:
                print(f"  Few posts detected, scrolling more aggressively...")
                scroll_times = SCROLLS_PER_PAGE * 2  # Double the scrolling
                min_pause = SCROLL_PAUSE_MIN * 0.5   # Reduce pause time
                max_pause = SCROLL_PAUSE_MAX * 0.8
            else:
                scroll_times = SCROLLS_PER_PAGE
                min_pause = SCROLL_PAUSE_MIN
                max_pause = SCROLL_PAUSE_MAX
            
            height_changed = scroll_page(page, scroll_times, min_pause, max_pause, debug=args.debug)
            
            if args.debug:
                scroll_after = page.evaluate("window.pageYOffset")
                height_after = page.evaluate("document.body.scrollHeight")
                print(f"  Scrolled from {scroll_before} to {scroll_after}, height change: {height_after - height_before}")

            # Expand truncated posts
            expanded = click_see_more(page)
            if expanded:
                print(f"  Expanded {expanded} 'See more' links")

            # Make sure we're still on the feed before extracting
            _dismiss_dialog(page)
            if not _is_on_feed(page):
                print("  Not on feed page, returning to feed...")
                success = _return_to_feed(page, debug=args.debug)
                if not success:
                    print("  ERROR: Failed to return to feed, stopping extraction")
                    break
                time.sleep(2)

            try:
                posts = extract_posts_from_page(page, debug=args.debug)
            except Exception as e:
                print(f"  ERROR: Failed to extract posts: {e}")
                if args.debug:
                    import traceback
                    traceback.print_exc()
                break
            
            if args.debug:
                # Check DOM state for debugging
                feed_stats = page.evaluate("""
                () => {
                    const feed = document.querySelector('[role="feed"]');
                    if (!feed) return {error: "No feed found"};
                    
                    const containers = [...feed.children];
                    let withPostLinks = 0;
                    let postIds = [];
                    let containerTypes = {};
                    
                    for (const c of containers) {
                        const postLink = c.querySelector('a[href*="/posts/"], a[href*="/permalink/"], a[href*="story_fbid"]');
                        if (postLink) {
                            withPostLinks++;
                            const href = postLink.href;
                            const idMatch = href.match(/posts\\/(\\d+)/) || href.match(/permalink\\/(\\d+)/) || href.match(/story_fbid=(\\d+)/);
                            if (idMatch) postIds.push(idMatch[1]);
                        } else {
                            // Analyze what type of non-post content this is
                            const text = c.innerText.toLowerCase();
                            const hasImages = c.querySelectorAll('img').length;
                            const hasLinks = c.querySelectorAll('a').length;
                            
                            let contentType = 'unknown';
                            if (text.includes('suggested for you') || text.includes('suggested post')) {
                                contentType = 'suggested_post';
                            } else if (text.includes('sponsored') || text.includes('ad')) {
                                contentType = 'ad';
                            } else if (text.includes('join group') || text.includes('invite')) {
                                contentType = 'invite_prompt';
                            } else if (text.includes('see more posts') || text.includes('load more')) {
                                contentType = 'load_more_prompt';
                            } else if (text.includes('people you may know') || text.includes('friend request')) {
                                contentType = 'people_suggestion';
                            } else if (hasImages > 0 && hasLinks > 2) {
                                contentType = 'media_content';
                            } else if (text.length < 50) {
                                contentType = 'ui_element';
                            } else {
                                contentType = 'other_content';
                            }
                            
                            containerTypes[contentType] = (containerTypes[contentType] || 0) + 1;
                        }
                    }
                    
                    // Check for "loading" indicators or infinite scroll triggers
                    const loadingEls = document.querySelectorAll('[role="progressbar"], [aria-label*="Loading"], [aria-label*="loading"]');
                    const hasLoadingIndicator = loadingEls.length > 0;
                    
                    // Check if we're at the bottom of loaded content
                    const scrollPosition = window.pageYOffset;
                    const windowHeight = window.innerHeight;
                    const documentHeight = document.documentElement.scrollHeight;
                    const distanceFromBottom = documentHeight - (scrollPosition + windowHeight);
                    
                    return {
                        totalContainers: containers.length,
                        withPostLinks: withPostLinks,
                        postIds: postIds,
                        containerTypes: containerTypes,
                        hasLoadingIndicator: hasLoadingIndicator,
                        scrollInfo: {
                            scrollPosition,
                            windowHeight,
                            documentHeight,
                            distanceFromBottom
                        }
                    };
                }
                """)
                print(f"  Debug: DOM analysis:")
                print(f"    - {feed_stats.get('totalContainers', 0)} containers in feed")
                print(f"    - {feed_stats.get('withPostLinks', 0)} with post links") 
                print(f"    - Posts extracted: {len(posts)}")
                print(f"    - Loading indicator present: {feed_stats.get('hasLoadingIndicator', False)}")
                print(f"    - Distance from bottom: {feed_stats.get('scrollInfo', {}).get('distanceFromBottom', 'unknown')}px")
                
                # Show what types of non-post content Facebook is showing
                container_types = feed_stats.get('containerTypes', {})
                if container_types:
                    print(f"    - Non-post container types: {dict(container_types)}")
                
                if feed_stats.get('postIds'):
                    print(f"    - Post IDs found: {feed_stats['postIds'][:5]}{'...' if len(feed_stats['postIds']) > 5 else ''}")
                    
                # Check if Facebook is limiting us due to rate limiting or bot detection
                if len(posts) < feed_stats.get('withPostLinks', 0):
                    print(f"    - WARNING: Found {feed_stats.get('withPostLinks', 0)} post containers but only extracted {len(posts)} posts")
                    print(f"    - This could indicate content restrictions or bot detection")
                

            # Merge with existing: add new posts, update existing ones if they changed
            new_count = 0
            updated_count = 0
            posts_needing_comments = []
            for post in posts:
                key = post.get("post_id") or post.get("text", "")[:100]
                if not key:
                    continue
                if key in posts_by_id:
                    # Compare with existing version and update if improved
                    idx = posts_by_id[key]
                    existing = all_posts[idx]
                    old_comments = len(existing.get("comments", []))
                    new_comments = len(post.get("comments", []))
                    old_text = existing.get("text", "")
                    new_text = post.get("text", "")
                    # Update if: more inline comments, longer text (was truncated),
                    # or text changed meaningfully
                    if (new_comments > old_comments
                            or len(new_text) > len(old_text)
                            or (new_text and new_text != old_text
                                and not old_text.startswith(new_text))):
                        # Preserve the richer comment list until we re-extract
                        if old_comments > new_comments:
                            post["comments"] = existing["comments"]
                        post["extracted_at"] = datetime.now(timezone.utc).isoformat()
                        all_posts[idx] = post
                        posts_needing_comments.append(post)
                        updated_count += 1
                else:
                    # Brand new post
                    posts_by_id[key] = len(all_posts)
                    all_posts.append(post)
                    posts_needing_comments.append(post)
                    new_count += 1

            print(f"  Found {len(posts)} posts on page, {new_count} new, {updated_count} updated, {len(all_posts)} total")

            # Extract full comments for new and updated posts
            # DISABLED: Opening new tabs for comment extraction interferes with main feed scrolling
            # if posts_needing_comments:
            #     n = len(posts_needing_comments)
            #     print(f"  Extracting comments for {n} posts...")
            #     for i, post in enumerate(posts_needing_comments):
            #         extract_comments_for_post(context, post, debug=args.debug)
            #         nc = len(post.get('comments', []))
            #         if nc > 0:
            #             print(f"    [{i+1}/{n}] {post.get('post_id', '?')}: {nc} comments")
            
            if posts_needing_comments and args.debug:
                print(f"  Skipping detailed comment extraction for {len(posts_needing_comments)} posts")
                print(f"  (Using inline comments only - to avoid tab switching that disrupts scrolling)")

            # Be more lenient about stopping - only stop if we found 0 posts total, or if height isn't changing
            if len(posts) == 0:  # Truly no posts found on page
                consecutive_empty += 1
                print(f"  No posts found on page (consecutive empty: {consecutive_empty})")
                if consecutive_empty >= 5:  # More lenient
                    print("  No posts found for 5 consecutive batches — stopping.")
                    break
            elif new_count == 0 and updated_count == 0:  # Found posts but all were duplicates
                consecutive_empty += 1
                print(f"  All posts were duplicates (consecutive stale: {consecutive_empty})")
                if not args.backfill and consecutive_empty >= 8:  # Much more lenient for duplicates
                    print("  No new posts for 8 consecutive batches — stopping.")
                    print("  (Use --backfill to keep scrolling past already-extracted posts)")
                    break
            else:
                consecutive_empty = 0

        browser.close()

    print(f"\nExtracted {len(all_posts)} total posts.")

    # Save with metadata envelope
    output = {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "group_url": GROUP_URL,
        "total_posts": len(all_posts),
        "posts": all_posts,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"Saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
