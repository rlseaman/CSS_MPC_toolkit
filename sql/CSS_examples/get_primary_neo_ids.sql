/* Query NEO orbits
 *
 *   usage: cat get_primary_neo_ids.sql | mysql -A -B -q -n -u neofixer -p<HIDDEN> -D mpc_development
 *
 * R. Seaman
 * 17 June 2021
 */

DROP TEMPORARY TABLE IF EXISTS tmporbs;

/* the orbits file has 136 (now more) duplicate / bollixed numbered NEO orbits,
 * with 1664 (now more) numbered duplicate orbits of all types
 * designation, number, and n_or_d are all fragile keys
 * packed_designation appears to be robust, unknown if complete (how would we know?)
 */
create temporary table tmporbs
  select

    # number,
    # designation,
    # name,
    # neo,
    # km_neo,
    # pha,
    # absolute_magnitude as H,
    # earth_moid as MOID,
    # perihelion_distance as q,
    # aphelion_distance as big_Q,
    # semimajor_axis as a,
    # eccentricity as e,
    # inclination as i,

    packed_designation as packed
  from
    orbits
  where
    neo
  and
    perihelion_distance <= 1.3
  group by
    packed_designation;

select distinct packed from tmporbs;

DROP TEMPORARY TABLE IF EXISTS tmporbs;

exit
