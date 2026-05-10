/*
drop function packnum(varchar(8));
 */

create or replace function packnum(number varchar(8))
  returns char(5)
  language plpgsql
as
$$
declare numnum integer;
declare num integer;

begin
  numnum := cast(number as integer);
  num := numnum / 10000;

  return
    case
      when numnum < 100000 then
	LPAD(number,5,'0')
      when numnum >= 100000 and numnum < 620000 then
	concat(
	  case
	    when (num >= 10 and num < 36) then chr(ascii('A') + num - 10)
	    when (num >= 36 and num < 62) then chr(ascii('a') + num - 36)
	  end,
	  LPAD(cast(mod(numnum,10000) as text),4,'0')
	)
      else
	concat('~',LPAD(base62_encode(numnum - 620000),4,'0'))
    end;
end;
$$;

CREATE OR REPLACE FUNCTION base62_encode(IN digits numeric, IN min_width int = 0) RETURNS text AS $$
DECLARE
    chars char[] := ARRAY['0','1','2','3','4','5','6','7','8','9','A','B'
                         ,'C','D','E','F','G','H','I','J','K','L','M','N'
                         ,'O','P','Q','R','S','T','U','V','W','X','Y','Z'
                         ,'a','b','c','d','e','f','g','h','i','j','k','l'
                         ,'m','n','o','p','q','r','s','t','u','v','w','x'
                         ,'y','z' ] ;  
    ret text:=''; 
    val numeric:= digits; 
BEGIN
    IF digits < 0 THEN 
        val := -val;
    END IF; 

    WHILE val > 0 OR min_width > 0 LOOP 
        ret := chars[(mod(val,62))+1] || ret; 
        val := div(val,62); 
        min_width := min_width-1;
    END LOOP;

    IF digits < 0 THEN 
        ret := '-'||ret; 
    END IF; 

    RETURN ret;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

/*
select packnum('612345') as test;
select packnum('623456') as test;
select packnum('625646') as test;
 */

select
  concat('"', packnum(max(b.permid)), '": [',
    string_agg(distinct format('"%s"',
      a.packed_secondary_provisional_designation),
      ','),
    '],') as links
from
  current_identifications a,
  numbered_identifications b
where
  b.permid ~ '^[0-9]+$'
/*
  ((b.permid ~ '^[0-9]+$')
     or
   substr(b.unpacked_primary_provisional_designation,1,1) in ('A','C','D','P','X','I'))
  b.permid ~ '^[0-9]+[ACDPXI]$'
  b.permid ~ '^[0-9]+$|^[0-9]+[ACDPXI]$'
 */
and
  a.packed_primary_provisional_designation = b.packed_primary_provisional_designation
group by
  b.permid
order by
  cast(b.permid as integer);
