<template>
  <div>
    <br>
    <b-container>
      <b-row>
        <b-col>
          <b-form-input
              placeholder="Enter search query"
              v-model="user_defined_query"
              type="text"
              @keyup.enter="searchCollection"
          >
          </b-form-input>
          <br>
          <label for="page-size">Max page size:&nbsp;</label>
          <b-form-input
              id="page-size"
              v-model="page_size"
              type="range" 
              min="1" 
              max="1000" 
              step="10">
          </b-form-input>
           {{ page_size }}
          <br>
          <br>
          <b-button
              @click="searchCollection"
          >
            Search
          </b-button>
          <div v-if="search_result.length != 0">
            <br><p class="text-secondary">Command-line equivalent:
            <br>{{curl_request}}</p>
          </div>
        </b-col>
        <b-col>
          <div v-if="operator_list.length != 0">
            <div>
              <b-table class="table-condensed" :items="operator_list" :fields="operator_list_fields" caption-top>
                <template #table-caption>Total Data Summary:</template>
              </b-table>
            </div>
          </div>
        </b-col>
      </b-row>
      <b-row>
        <b-col>
          <div>
            <div>
              <b-table :items="search_result" :fields="search_result_fields" :busy="isBusy" caption-top>
                <template #table-caption>Search results:</template>
                <template #table-busy>
                  <div>
                    <b-spinner class="align-middle"></b-spinner>
                    <strong>&nbsp; Loading...</strong>
                  </div>
                </template>
              </b-table>
              <p v-if="search_result.length === 0 && isBusy === false" style="text-align: left" class="text-secondary">No results</p>
            </div>
          </div>
        </b-col>
      </b-row>
    </b-container>
  </div>
</template>

<script>

export default {
  name: 'Search',
  data () {
    return {
      isBusy: false,
      curl_request: "",
      page_size: 100,
      user_defined_query: "",
      search_result: [],
      search_result_fields: [],
      operator_list: [],
      operator_list_fields: [{key: "key", label: "Operator"}, {key: "doc_count"}],
    }
  },
  computed: {
      
  },
  created: function () {
    this.getDataSummary()
  },
  methods: {
    async getDataSummary () {
      var data = {
        "size": 0,
        "aggs" : {
          "unique_operators": {
            "terms": {
              "field": "Operator.keyword"
            }
          }
        }
      };
      fetch(process.env.VUE_APP_OPENSEARCH_ENDPOINT+'/_search', {
        method: 'post',
        body: JSON.stringify(data),
        headers: {'Content-Type': 'application/json'}
      }).then(response =>
          response.json().then(data => ({
                data: data,
                status: response.status
              })
          ).then(res => {
            if (res.status == 403) {
              this.showElasticSearchAlert = true
            } else {
              console.log("data summary search returned the following data:")
              console.log(res)
              console.log(res.data.aggregations.unique_operators.buckets.length)
              this.operator_list = res.data.aggregations.unique_operators.buckets
            }
          })
      )
    },

    async searchCollection () {
      this.isBusy = true
      this.curl_request = "curl -X POST \"" + process.env.VUE_APP_OPENSEARCH_ENDPOINT + "/_search?q=" + this.user_defined_query + "\" -H 'Content-Type: application/json' -d '{\"size\":" + this.page_size + "}' | jq"
      var data = {
        "size": this.page_size
      };
      fetch(process.env.VUE_APP_OPENSEARCH_ENDPOINT+'/_search?q=' + this.user_defined_query, {
        method: 'post',
        body: JSON.stringify(data),
        headers: {'Content-Type': 'application/json'}
      }).then(response =>
        response.json().then(data => ({
              data: data,
              status: response.status
            })
        ).then(res => {
          this.isBusy = false
          if (res.status == 403) {
            this.showElasticSearchAlert = true
          }
          if (!res.data) {
            console.log("the search returned no data")
            
          } else {
            console.log("the search returned the following data:")
            console.log(res.data.hits.hits.map(x => x._source)[0])
            console.log(res.data.hits.hits.length)
            this.search_result = res.data.hits.hits.map(x => x._source)
          }
        })
      )
    },
  }
}
</script>

<!-- Add "scoped" attribute to limit CSS to this component only -->
<style scoped>
.table-condensed {
  font-size: 12px;
}
</style>
