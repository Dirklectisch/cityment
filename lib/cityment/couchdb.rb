require 'yajl'
require 'cityment/datetime'
require 'rufus/verbs'

module Cityment
  
  class CouchDB
    attr_reader :encoder, :endpoint
    
    def initialize debug = false
      
      @endpoint = Rufus::Verbs::EndPoint.new(
                    :host => 'localhost',
                    :port => '5984',
                    :base => 'cityment',
                    :h => {'accept' => 'application/json'})
      
      @endpoint.parsers['application/json'] = Yajl::Parser
      
      if debug == true
        @encoder = Yajl::Encoder.new :pretty => true
        @endpoint.opts[:dry_run] = true
      else
        @encoder = Yajl::Encoder.new
      end
    end
    
    def encode body, head = {}
      head.merge! body
      encoder.encode(head) # {"title" => "...", "date" => "..."}
    end
    
    def uuid
      resp = endpoint.get :base => '', :resource => '_uuids', :h => {'accept' => 'application/json'}
      resp = resp[:uuids].to_s unless endpoint.opts[:dry_run] == true
      resp
    end
    
    def create item
      req = encode(item, {:_id => uuid})
      endpoint.post(:h => {'content-type' => 'application/json'}, :data => req)
    end
    
    def saved_dates
      first = endpoint.get(:id => '/_design/all/_view/by_date?limit=1', :h => {'accept' => 'application/json'})
      first = first.body['rows'].first['key']
      first_dt = DateTime.from_json(first)
      
      last = endpoint.get(:id => '/_design/all/_view/by_date?limit=1&descending=true', :h => {'accept' => 'application/json'})
      last = last.body['rows'].last['key']
      last_dt = DateTime.from_json(last)
      
      range = first_dt..last_dt
    end
  end # CouchDB
  
  DB = CouchDB.new
  
end