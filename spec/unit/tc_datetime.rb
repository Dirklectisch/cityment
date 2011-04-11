require 'minitest/autorun'
require 'cityment/datetime'

describe DateTime do
  describe :api_format do
    it "formats a string expected by AT5 API" do
      dt = DateTime.parse("2009-01-01T13:00:00+00:00")
      assert_equal(dt.at5_api_format, "2009-01-01 13:00:00")
    end
  end
  describe :stamp do
    it "returns a date stamp" do
      dt = DateTime.parse("2009-01-01T13:00:00+00:00")
      assert_equal(dt.stamp, '20090101130000')
    end
  end
end

describe String do
  describe :to_datetime do
    it "parses the string to a DateTime object" do
     str = '2009-01-01'
     assert(str.to_datetime.kind_of? DateTime) 
    end
  end
end