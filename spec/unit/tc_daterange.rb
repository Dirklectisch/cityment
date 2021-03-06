require 'minitest/autorun'
require 'cityment/daterange'

include Cityment

describe DateRange do
  describe :complete_range do
    it 'returns a range between 2007-01-01 and today' do
      range = DateRange.complete_range
      assert_equal(range.min, Date.parse('2007-01-01'))
    end
    it 'extends the range with DateRange module' do
      range = DateRange.complete_range
      assert(range.respond_to? :each_month)
    end
    it 'sets a custom start date' do
      start_date = Date.parse('2011-01-01')
      range = DateRange.complete_range(start_date)
      assert_equal(range.first, start_date)
    end
  end
  describe :each_year do
    it "it yields sub-ranges by year" do
      first = Date.parse('2009-01-01')
      last = Date.parse('2011-01-01')
      complete_range = first...last
      
      complete_range.extend DateRange
      sub_ranges = complete_range.each_year.to_a
      
      assert_equal(sub_ranges[0].max, Date.parse('2009-12-31'))
      assert_equal(sub_ranges[1].min, Date.parse('2010-01-01'))
    end
    it "extends yielded range with DateRange mixin" do
      range = DateRange.complete_range(Date.parse('2011-01-01'))
      sub_ranges = range.each_year.to_a
      assert(sub_ranges.sample.respond_to? :crawl)      
    end
  end
  describe :each_month do
    it "yields sub-ranges by month" do
      first = Date.parse('2009-01-01')
      last = Date.parse('2011-01-01')
      complete_range = first...last
      
      complete_range.extend DateRange
      sub_ranges = complete_range.each_month.to_a
      
      assert_equal(sub_ranges.count, 24)
    end
    it "extends yielded range with DateRange mixin" do
      range = DateRange.complete_range(Date.parse('2011-01-01'))
      sub_ranges = range.each_month.to_a
      assert(sub_ranges.sample.respond_to? :crawl)      
    end
  end
  describe :crawl do
    it "yields next range according to returned fetched range" do
      first = Date.parse('2009-01-01')
      last = Date.parse('2009-04-01')
      range = (first...last).extend DateRange
      
      months = range.each_month{|r| r}.reverse
      requests_made = []
      requests_made_fixture = [Date.parse('2009-01-01')...Date.parse('2009-04-01'),
                               Date.parse('2009-01-01')...Date.parse('2009-03-01'),
                               Date.parse('2009-01-01')...Date.parse('2009-02-01')]
      
      range.crawl do |request_range|
        request_count = requests_made.count
        requests_made << request_range
        fetched_range = months[request_count]
      end 
      
      assert_equal(requests_made, requests_made_fixture)       
    end
    it "yields only one range when exact range is returned" do
      first = Date.parse('2009-01-01')
      last = Date.parse('2009-04-01')
      range = (first...last).extend DateRange
      
      requests_made = []
      requests_made_fixture = [Date.parse('2009-01-01')...Date.parse('2009-04-01')]
      
      range.crawl do |request_range|
        requests_made << request_range
        request_range
      end
      
      assert_equal(requests_made_fixture, requests_made)  
    end 
  end
  describe :umbrella? do
    it "returns true if other range is within self" do
      range = (Date.parse('2009-01-01')...Date.parse('2009-04-01')).extend DateRange    
      other = Date.parse('2009-02-01')...Date.parse('2009-03-01')
      
      assert(range.umbrella?(other) == true)
    end
    it "returns false if other range is not within self" do
      range = (Date.parse('2009-02-01')...Date.parse('2009-03-01')).extend DateRange
      other = Date.parse('2009-01-01')...Date.parse('2009-04-01')

      assert(range.umbrella?(other) == false)      
    end
  end
end