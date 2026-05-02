/*
 * sudo -u postgres psql -A -t -q -h sibyl mpc_sbn < getneos_80col_obs_sbn.sql > /home/fixer/neofixer/external/catalog/postgres_allneos.ast
 */

CREATE TEMPORARY TABLE nf_neos (nid text);
  \copy nf_neos FROM '/home/fixer/neofixer/external/catalog/primary_neo_unpacked.txt';
  CREATE INDEX nid_index ON nf_neos (nid);

CREATE TEMPORARY TABLE nf_extras (eid text);
  \copy nf_extras FROM '/home/fixer/neofixer/external/catalog/extras.unpack';
  CREATE INDEX eid_index ON nf_extras (eid);

CREATE TEMPORARY TABLE nf_astrometry (obs80 text, rmsra numeric, rmsdec numeric);

/* get astrometry for unnumbered comets, not sure if there should ever be secondary designations
 */
INSERT INTO nf_astrometry
  select obs80, rmsra, rmsdec from obs_sbn where provid in (select * from nf_neos where strpos(nid,' ') = 7) and status in ('P','p');

INSERT INTO nf_astrometry
  select obs80, rmsra, rmsdec from obs_sbn where provid in (select * from nf_neos where strpos(nid,' ') = 5) and status in ('P','p');

INSERT INTO nf_astrometry
  select obs80, rmsra, rmsdec from obs_sbn where provid in (select * from nf_extras where strpos(eid,' ') = 5) and status in ('P','p');

INSERT INTO nf_astrometry
  select obs80, rmsra, rmsdec from obs_sbn where permid in (select * from nf_neos where strpos(nid,' ') = 0) and status in ('P','p');

INSERT INTO nf_astrometry
  select obs80, rmsra, rmsdec from obs_sbn where permid in (select * from nf_extras where strpos(eid,' ') = 0) and status in ('P','p');

/*
  CREATE INDEX  obs80_index ON nf_astrometry (obs80);
 */
  CREATE INDEX  rmsra_index ON nf_astrometry (rmsra);
  CREATE INDEX rmsdec_index ON nf_astrometry (rmsdec);

/* should validate each record for diverse issues, starting with length = 80|160, etc.
 */
select
/*
  case when  rmsra is null then '-9999' else rmsra end, 
  case when rmsdec is null then '-9999' else rmsdec end,
 */

  case
    when
      rmsra is null or rmsdec is null
    then
      concat(substr(obs80,1,80), '\n', substr(obs80,81), case when length(obs80) = 160 then '\n' end)

    else
      /* if rmsra and rmsdec are kept < 10" (below), don't need units other than the default float seconds
       */
      case when length(obs80) = 160 then
	concat(substr(obs80,1,56), 
	  case when rmsra  < 1 and rmsdec < 1 then
	    concat(' ', to_char(rmsra*1000, 'FM000'), ' ', to_char(rmsdec*1000,'FM000'), 'm')
	  else
	    concat(to_char(rmsra, 'FM0.00'), ' ', to_char(rmsdec,'FM0.00'))
	  end,
	  substr(obs80,66,15), '\n', substr(obs80,81), '\n')

      else
	concat(substr(obs80,1,56), 
	  case when rmsra  < 1 and rmsdec < 1 then
	    concat(' ', to_char(rmsra*1000, 'FM000'), ' ', to_char(rmsdec*1000,'FM000'), 'm')
	  else
	    concat(to_char(rmsra, 'FM0.00'), ' ', to_char(rmsdec,'FM0.00'))
	  end,
	  substr(obs80,66,15), '\n')
      end

  end

from
  (select
    distinct obs80,
    rmsra,
    rmsdec
  from
    nf_astrometry
  where
    (rmsra is null or rmsra < 5.0)
  and
    (rmsdec is null or rmsdec < 5.0)
  and
    substr(obs80,15,1) not in ('X','x')
  ) as a;
