/**
 * Format a date string into a human-friendly relative time.
 */
export default function timeAgo(dateString) {
  if (!dateString) return "";
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now - date) / 1000);

  if (seconds < 60) return "just now";
  if (seconds < 3600) {
    const m = Math.floor(seconds / 60);
    return `${m} minute${m !== 1 ? "s" : ""} ago`;
  }
  if (seconds < 86400) {
    const h = Math.floor(seconds / 3600);
    return `${h} hour${h !== 1 ? "s" : ""} ago`;
  }
  if (seconds < 172800) return "yesterday";
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}
