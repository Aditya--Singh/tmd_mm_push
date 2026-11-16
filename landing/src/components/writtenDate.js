/**
 * Dates, as they are written in the landing page.
 *
 * The dates are written out by hand, because the way a date is written by the
 * browser depends on the version of the language data it carries, and the same
 * day would then be read differently on different machines.
 */

const MONTHS = [
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
];

/**
 * A date as it is shown to the reader: 13 Oct 2026.
 *
 * @param {Date|string|number} value - the date to write.
 */
export function writtenDate(value) {
    const date = value instanceof Date ? value : new Date(value);

    if (Number.isNaN(date.getTime())) {
        return "";
    }

    const day = String(date.getDate()).padStart(2, "0");

    return `${day} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}
