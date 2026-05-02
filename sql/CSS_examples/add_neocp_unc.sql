/*
 * sudo -u postgres psql -f add_neocp_unc.sql -A -t -q -h sibyl mpc_sbn < /home/fixer/nf/objects/neocp/P21SWrw/P21SWrw.obs.txt > P21SWrw.out.txt
 */

/* \copy doesn't allow variable expansion
 * concurrency of temporary tables?
 */

/*
  \copy nf_obs FROM '/home/fixer/nf/objects/neocp/P21SWrw/P21SWrw.obs.txt';
 */

CREATE TEMPORARY TABLE nf_obs (obs80 text);
  \copy nf_obs FROM pstdin;

CREATE TEMPORARY TABLE nf_astrometry (obs80 text, rmsra numeric, rmsdec numeric);

INSERT INTO nf_astrometry
  select
    obs80, rmsra, rmsdec
  from
    /* obs_sbn, neocp_obs_archive */
    neocp_obs
  where
    /* might be worth doing this as an explicit join, but seems fast enough */
    substr(obs80,1,12) in (select substr(obs80,1,12) from nf_obs)
  and
    substr(obs80,15,42) in (select substr(obs80,15,42) from nf_obs)
  and
    substr(obs80,78,3) in (select substr(obs80,78,3) from nf_obs);

/*
select 'input:';
select * from nf_obs order by substr(obs80,16,17);

select 'matching fields:';
select substr(obs80,1,12), '', substr(obs80,15,57), '    ', substr(obs80,78,3) from nf_obs order by substr(obs80,16,17);
select substr(obs80,1,12), '', substr(obs80,15,42), '                   ', substr(obs80,78,3) from nf_obs;

select 'output:';
select * from nf_astrometry;
 */

/* one wonders if postgres has facilities to verify inputs and outputs
 */

select
  case
    when
      rmsra is null or rmsdec is null
    then
      /* note the explicit embedded newline to get a second line on output
       * could also use an extended constant, backslash escape doesn't work in SQL
       */
      case when length(obs80) = 160 then
	concat(substr(obs80,1,80), chr(10), substr(obs80,81))
      else
	obs80
      end

    else
      case when length(obs80) = 160 then
	concat(substr(obs80,1,56), 
	  case
	  when rmsra  >= 10 or rmsdec >= 10 then
	    concat(to_char(rmsra, '999'), to_char(rmsdec,'999'), ' ')
	  when rmsra  < 1 and rmsdec < 1 then
	    concat(' ', to_char(rmsra*1000, 'FM000'), ' ', to_char(rmsdec*1000,'FM000'), 'm')
	  else
	    concat(to_char(rmsra, 'FM0.00'), ' ', to_char(rmsdec,'FM0.00'))
	  end,
	  substr(obs80,66,15), chr(10), substr(obs80,81))

      else
	concat(substr(obs80,1,56), 
	  case
	  when rmsra  >= 10 or rmsdec >= 10 then
	    concat(to_char(rmsra, '999'), to_char(rmsdec,'999'), ' ')
	  when rmsra  < 1 and rmsdec < 1 then
	    concat(' ', to_char(rmsra*1000, 'FM000'), ' ', to_char(rmsdec*1000,'FM000'), 'm')
	  else
	    concat(to_char(rmsra, 'FM0.00'), ' ', to_char(rmsdec,'FM0.00'))
	  end,
	  substr(obs80,66,15))
      end

  end

from
  (select obs80, rmsra, rmsdec from nf_astrometry) as a

order by
  /* reorder by time, preserving roving format order (first col 15 is capital, second is lower case)
   * throw in a sort by stn in case there are simultaneous observations from multiple stations
   * assumes no telescope can self-conflict with a differing col 15
   * but there are still duplicates that are unrelated (I think) to this
   * may want to filter output for distinct substring?!?
   */
  substr(obs80,16,17), substr(obs80,15,1), substr(obs80,78,3);
