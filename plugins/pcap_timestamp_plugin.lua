local UINT32_BASE = 4294967296
local MICROSECONDS_PER_SECOND = 1000000
local NANOSECONDS_PER_SECOND = 1000000000

local function transform_timestamps(instance, transform_pcap, transform_pcapng)
	local seconds_index, seconds_field
	local nanoseconds_index, nanoseconds_field
	local high_index, high_field
	local low_index, low_field
	for index = 0, #instance.field_instances - 1 do
		local field = instance.field_instances[index]
		if field.field_def.name == "timestamp_seconds" then
			seconds_index, seconds_field = index, field
		elseif field.field_def.name == "timestamp_nanoseconds" then
			nanoseconds_index, nanoseconds_field = index, field
		elseif field.field_def.name == "high" then
			high_index, high_field = index, field
		elseif field.field_def.name == "low" then
			low_index, low_field = index, field
		elseif field.is_struct then
			transform_timestamps(field.value, transform_pcap, transform_pcapng)
		end
	end
	if seconds_field and nanoseconds_field then
		transform_pcap(
			instance,
			seconds_index,
			seconds_field,
			nanoseconds_index,
			nanoseconds_field
		)
	elseif high_field and low_field then
		transform_pcapng(
			instance,
			high_index,
			high_field,
			low_index,
			low_field
		)
	end
end

local function format_timestamp(seconds, nanoseconds)
	return os.date("!%Y-%m-%d %H:%M:%S", seconds) ..
		string.format(".%09d", nanoseconds)
end

local function pcapng_units_per_second(timestamp)
	if timestamp >= 100000000000000000 then
		return NANOSECONDS_PER_SECOND
	end
	return MICROSECONDS_PER_SECOND
end

local function utc_to_epoch(timestamp)
	local year = timestamp.year
	local month = timestamp.month
	year = year - (month <= 2 and 1 or 0)
	local era = (year >= 0 and year or year - 399) // 400
	local year_of_era = year - era * 400
	local month_of_year = month + (month > 2 and -3 or 9)
	local day_of_year =
		(153 * month_of_year + 2) // 5 + timestamp.day - 1
	local day_of_era = year_of_era * 365 + year_of_era // 4 -
		year_of_era // 100 + day_of_year
	local days = era * 146097 + day_of_era - 719468
	return days * 86400 + timestamp.hour * 3600 +
		timestamp.min * 60 + timestamp.sec
end

local function parse_timestamp(value)
	local year, month, day, hour, minute, second, nanoseconds =
		value:match(
			"(%d+)%-(%d+)%-(%d+) (%d+):(%d+):(%d+)%.(%d+)"
		)
	local seconds = utc_to_epoch({
		year = tonumber(year),
		month = tonumber(month),
		day = tonumber(day),
		hour = tonumber(hour),
		min = tonumber(minute),
		sec = tonumber(second),
	})
	return seconds, tonumber(nanoseconds)
end

return {
	decode = function(instance)
		transform_timestamps(
			instance,
			function(timestamp, _, seconds_field, _, nanoseconds_field)
				timestamp.display_value = format_timestamp(
					seconds_field.value,
					nanoseconds_field.value
				)
			end,
			function(timestamp, _, high_field, _, low_field)
				local raw_value = high_field.value * UINT32_BASE + low_field.value
				local units_per_second = pcapng_units_per_second(raw_value)
				local seconds = raw_value // units_per_second
				local fraction = raw_value % units_per_second
				local nanoseconds = fraction *
					(NANOSECONDS_PER_SECOND // units_per_second)
				timestamp.display_value = format_timestamp(seconds, nanoseconds)
			end
		)
		return instance
	end,
	encode = function(instance)
		transform_timestamps(
			instance,
			function(timestamp, seconds_index, seconds_field,
					nanoseconds_index, nanoseconds_field)
				if timestamp.display_value == nil then return end
				local seconds, nanoseconds = parse_timestamp(timestamp.display_value)
				timestamp.field_instances[seconds_index] =
					seconds_field:with_value(seconds)
				timestamp.field_instances[nanoseconds_index] =
					nanoseconds_field:with_value(nanoseconds)
			end,
			function(timestamp, high_index, high_field, low_index, low_field)
				if timestamp.display_value == nil then return end
				local raw_value = high_field.value * UINT32_BASE + low_field.value
				local units_per_second = pcapng_units_per_second(raw_value)
				local seconds, nanoseconds = parse_timestamp(timestamp.display_value)
				local encoded_value = seconds * units_per_second +
					nanoseconds //
					(NANOSECONDS_PER_SECOND // units_per_second)
				timestamp.field_instances[high_index] =
					high_field:with_value(encoded_value // UINT32_BASE)
				timestamp.field_instances[low_index] =
					low_field:with_value(encoded_value % UINT32_BASE)
			end
		)
		return instance
	end,
}