/* cat getneos_80col.sql | mysql -N -s -u neofixer -p<pw> mpc_development > <output file>
 *
 * output records retain newlines (end of record and embedded between double records for C51, etc)
 *
 * R. Seaman, 21Sep22
 */

DROP TEMPORARY TABLE IF EXISTS extras;
DROP TEMPORARY TABLE IF EXISTS blocked;

/* Extras is an externally created list of unpacked NEO designations,
 * for example, from the PostgreSQL tables of secondary designations.
 * There don't appear to be any extra numbered tracklets in the
 * either the PostgreSQL tables or the MariaDB observations table.
 */

CREATE TEMPORARY TABLE extras (designation VARCHAR(20));
CREATE TEMPORARY TABLE blocked (designation VARCHAR(20));

/* MySQL security model would require dynamic proc to handle the pathnames as
 * variables rather than string literals. Could also use symlinks at the host level.
 */
LOAD DATA LOCAL INFILE '/home/fixer/neofixer/external/catalog/extras.unpack' INTO TABLE extras;
LOAD DATA LOCAL INFILE '/home/fixer/neofixer/configs/blocked.unpack' INTO TABLE blocked;

select
  obs

from (

    select
      original_record as obs
    from
      observations
    where
      number in
	(select number from orbits where neo and designation is null)

    /* might need blocked numbers, too */

  union

    select
      original_record as obs
    from
      observations
    where
      designation in
	(select designation from orbits where neo and number is null)
    and
      designation not in
	(select designation from blocked)

  union

    select
      original_record as obs
    from
      observations
    where
      designation in
	(select designation from extras)

    /* might also need to search for extra numbered objects and/or
     * in the first 12 characters of original_record (very expensive)
     */

  ) as a;

/*
order by
  substr(obs,1,5),
  substr(obs,6,7) desc,
  substr(obs,16,16);
 */

DROP TEMPORARY TABLE IF EXISTS extras;
DROP TEMPORARY TABLE IF EXISTS blocked;
